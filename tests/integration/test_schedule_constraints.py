"""Ограничения расписания на реальной PostgreSQL (T3.01, docs/04 §4.1)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import AttendanceStatus, LessonStatus, UserRole
from src.db.models import Lesson, LessonParticipant, ScheduleTemplate, Subject, User

START = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


@pytest.fixture
async def teacher(db_session: AsyncSession) -> User:
    user = User(role=UserRole.OWNER, display_name="Роман")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def subject(db_session: AsyncSession) -> Subject:
    item = Subject(code="informatics_t301", name="Информатика")
    db_session.add(item)
    await db_session.flush()
    return item


def _lesson(
    teacher: User,
    subject: Subject,
    start: datetime = START,
    minutes: int = 60,
    **extra: object,
) -> Lesson:
    return Lesson(
        teacher_id=teacher.id,
        subject_id=subject.id,
        start_at=start,
        end_at=start + timedelta(minutes=minutes),
        **extra,
    )


async def test_overlapping_lessons_of_one_teacher_are_rejected(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    db_session.add(_lesson(teacher, subject))
    await db_session.flush()
    async with db_session.begin_nested():
        db_session.add(_lesson(teacher, subject, START + timedelta(minutes=30)))
        with pytest.raises(IntegrityError, match="ex_lessons_teacher_no_overlap"):
            await db_session.flush()


async def test_back_to_back_and_cancelled_lessons_do_not_conflict(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    db_session.add(_lesson(teacher, subject))
    db_session.add(_lesson(teacher, subject, START + timedelta(hours=1)))  # встык
    db_session.add(
        _lesson(teacher, subject, START + timedelta(minutes=10), 20, status=LessonStatus.CANCELLED)
    )
    await db_session.flush()


async def test_other_teacher_can_use_same_time(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    other = User(role=UserRole.MANAGER, display_name="Мария")
    db_session.add(other)
    await db_session.flush()
    db_session.add(_lesson(teacher, subject))
    db_session.add(_lesson(other, subject))
    await db_session.flush()


async def test_lesson_must_end_after_start(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    async with db_session.begin_nested():
        db_session.add(_lesson(teacher, subject, minutes=0))
        with pytest.raises(IntegrityError, match="ck_lessons_end_after_start"):
            await db_session.flush()


async def test_template_lesson_start_is_unique_per_template(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    template = ScheduleTemplate(
        teacher_id=teacher.id,
        subject_id=subject.id,
        weekday=1,
        start_local_time=START.time(),
        duration_minutes=60,
        timezone="Europe/Moscow",
        starts_on=START.date(),
    )
    db_session.add(template)
    await db_session.flush()
    db_session.add(_lesson(teacher, subject, template_id=template.id))
    await db_session.flush()
    async with db_session.begin_nested():
        # Тот же шаблон и то же начало: идемпотентность генерации (пересечение здесь тоже есть).
        db_session.add(_lesson(teacher, subject, template_id=template.id))
        with pytest.raises(IntegrityError):
            await db_session.flush()


@pytest.mark.parametrize("weekday", [0, 8])
async def test_template_weekday_is_1_to_7(
    db_session: AsyncSession, teacher: User, subject: Subject, weekday: int
) -> None:
    async with db_session.begin_nested():
        db_session.add(
            ScheduleTemplate(
                teacher_id=teacher.id,
                subject_id=subject.id,
                weekday=weekday,
                start_local_time=START.time(),
                timezone="Europe/Moscow",
                starts_on=START.date(),
            )
        )
        with pytest.raises(IntegrityError, match="ck_schedule_templates_weekday_range"):
            await db_session.flush()


async def test_template_defaults_and_participant_defaults(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    student = User(role=UserRole.STUDENT, display_name="Аня")
    db_session.add(student)
    await db_session.flush()
    template = ScheduleTemplate(
        teacher_id=teacher.id,
        subject_id=subject.id,
        weekday=2,
        start_local_time=START.time(),
        timezone="Europe/Moscow",
        starts_on=START.date(),
    )
    lesson = _lesson(teacher, subject)
    db_session.add_all([template, lesson])
    await db_session.flush()
    db_session.add(LessonParticipant(lesson_id=lesson.id, student_id=student.id))
    await db_session.flush()
    await db_session.refresh(template)
    await db_session.refresh(lesson)
    assert template.duration_minutes == 60
    assert template.is_active is True
    assert lesson.status == LessonStatus.SCHEDULED
    assert lesson.is_detached is False
    row = (await db_session.execute(select(LessonParticipant))).scalar_one()
    assert row.attendance == AttendanceStatus.PENDING
    assert row.is_billable is False
    assert row.price_snapshot is None


async def test_negative_price_snapshot_is_rejected(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    student = User(role=UserRole.STUDENT, display_name="Аня")
    db_session.add(student)
    lesson = _lesson(teacher, subject)
    db_session.add(lesson)
    await db_session.flush()
    async with db_session.begin_nested():
        db_session.add(
            LessonParticipant(lesson_id=lesson.id, student_id=student.id, price_snapshot=-1)
        )
        with pytest.raises(IntegrityError, match="price_snapshot_nonneg"):
            await db_session.flush()
