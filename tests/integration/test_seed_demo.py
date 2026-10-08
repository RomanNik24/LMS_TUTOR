"""Скрипт демо-данных (T7.05): создание, ``--purge``, защита от чужих данных и от prod."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import UserRole
from src.db.models import (
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    MockExamResult,
    StudentProfile,
    Subject,
    User,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_demo", ROOT / "scripts/seed_demo.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


async def _count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.fixture
async def owner(db_session: AsyncSession, seeded_reference: object) -> User:
    user = User(role=UserRole.OWNER, display_name="Владелец", telegram_id=11)
    db_session.add(user)
    await db_session.commit()
    return user


async def _real_student(db: AsyncSession, owner: User) -> User:
    user = User(role=UserRole.STUDENT, display_name="Настоящий", telegram_id=555)
    db.add(user)
    await db.flush()
    db.add(StudentProfile(user_id=user.id, teacher_id=owner.id, lesson_price=1700))
    await db.commit()
    return user


async def test_seed_creates_marked_data_and_purge_removes_only_it(
    db_session: AsyncSession, owner: User
) -> None:
    real = await _real_student(db_session, owner)
    subject = (await db_session.execute(select(Subject).limit(1))).scalar_one()
    # настоящий урок владельца в окне демо-данных: слот должен быть пропущен без конфликта
    lesson = Lesson(
        teacher_id=owner.id,
        subject_id=subject.id,
        start_at=NOW,
        end_at=NOW.replace(hour=11),
    )
    db_session.add(lesson)
    await db_session.flush()
    db_session.add(LessonParticipant(lesson_id=lesson.id, student_id=real.id))
    await db_session.commit()

    stats = await script.seed_demo(db_session, students=100, now=NOW)

    assert stats.students == 100
    assert stats.lessons > 300
    assert stats.assignments >= 300
    assert stats.mock_exams > 100
    demo_ids = await script._demo_student_ids(db_session)
    assert len(demo_ids) == 100
    assert await _count(db_session, StudentProfile) == 101
    # у настоящего ученика нет признаков демо, его данные на месте
    assert real.id not in demo_ids

    purged = await script.purge_demo(db_session)
    await db_session.commit()

    assert purged.students == 100
    assert await script._demo_student_ids(db_session) == []
    assert await _count(db_session, StudentProfile) == 1
    assert await _count(db_session, MockExamResult) == 0
    assert await _count(db_session, HomeworkAssignment) == 0
    assert await _count(db_session, Homework) == 0
    assert await _count(db_session, Lesson) == 1  # остался только настоящий урок
    assert await _count(db_session, LessonParticipant) == 1
    assert (await db_session.get(User, real.id)) is not None


async def test_seed_does_not_overlap_owner_lessons(db_session: AsyncSession, owner: User) -> None:
    await script.seed_demo(db_session, students=100, now=NOW)

    rows = (
        await db_session.execute(
            select(Lesson.start_at, Lesson.end_at)
            .where(Lesson.teacher_id == owner.id)
            .order_by(Lesson.start_at)
        )
    ).all()
    for (_, previous_end), (next_start, _) in zip(rows, rows[1:], strict=False):
        assert next_start >= previous_end


async def test_seed_refuses_twice_and_without_owner_or_reference(
    db_session: AsyncSession, owner: User
) -> None:
    await script.seed_demo(db_session, students=5, now=NOW)

    with pytest.raises(script.DevScriptError, match="purge"):
        await script.seed_demo(db_session, students=5, now=NOW)
    with pytest.raises(script.DevScriptError):
        await script.seed_demo(db_session, students=101, now=NOW)
    with pytest.raises(script.DevScriptError):
        await script.seed_demo(db_session, students=0, now=NOW)


async def test_seed_requires_owner(db_session: AsyncSession) -> None:
    with pytest.raises(script.DevScriptError, match="владельца"):
        await script.seed_demo(db_session, students=3, now=NOW)


def test_refuses_in_prod_before_any_connection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")

    assert script.main(["--students", "5"]) == script.EXIT_REFUSED
    assert script.main(["--purge"]) == script.EXIT_REFUSED
    assert "APP_ENV=prod" in capsys.readouterr().out
