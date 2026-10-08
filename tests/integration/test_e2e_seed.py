"""Скрипт пользователей для E2E (T8.07): идемпотентность, purge, защита от prod."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import UserRole
from src.db.models import StudentProfile, Subject, User

ROOT = Path(__file__).resolve().parents[2]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("e2e_seed", ROOT / "scripts/e2e_seed.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


async def users(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(User))).scalar_one()


async def test_seed_creates_owner_and_student_once(db_session: AsyncSession) -> None:
    db_session.add(Subject(code="informatics", name="Информатика"))
    await db_session.commit()

    first = await script.seed_e2e(db_session, owner_tg_id=900_000_001, student_tg_id=900_000_002)
    second = await script.seed_e2e(db_session, owner_tg_id=900_000_001, student_tg_id=900_000_002)

    assert first == second
    assert await users(db_session) == 2
    owner = await db_session.get(User, first[0])
    student = await db_session.get(User, first[1])
    assert owner is not None
    assert student is not None
    assert (owner.role, owner.telegram_id) == (UserRole.OWNER, 900_000_001)
    assert (student.role, student.display_name) == (UserRole.STUDENT, "E2E Ученик")
    assert await db_session.get(StudentProfile, student.id) is not None


async def test_purge_removes_only_e2e_users(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            Subject(code="informatics", name="Информатика"),
            User(role=UserRole.OWNER, display_name="Настоящий", telegram_id=42),
        ]
    )
    await db_session.commit()
    await script.seed_e2e(db_session, owner_tg_id=900_000_001, student_tg_id=900_000_002)

    removed = await script.purge_e2e(db_session)
    await db_session.commit()

    assert removed == 2
    assert await users(db_session) == 1


async def test_refuses_without_reference_and_with_taken_telegram_id(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(script.E2eSeedError, match="справочников"):
        await script.seed_e2e(db_session, owner_tg_id=1, student_tg_id=2)

    db_session.add_all(
        [
            Subject(code="informatics", name="Информатика"),
            User(role=UserRole.OWNER, display_name="Настоящий", telegram_id=900_000_001),
        ]
    )
    await db_session.commit()
    with pytest.raises(script.E2eSeedError, match="занят"):
        await script.seed_e2e(db_session, owner_tg_id=900_000_001, student_tg_id=900_000_002)


def test_refuses_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")

    assert script.main([]) == script.EXIT_REFUSED
    assert script.main(["--purge"]) == script.EXIT_REFUSED
