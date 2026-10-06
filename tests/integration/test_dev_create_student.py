"""Тесты dev-скрипта создания тестового ученика (T1.14a)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import UserRole
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.models import AuditLog, StudentProfile, User
from src.services.auth import AuthService, InviteAcceptStatus

ROOT = Path(__file__).resolve().parents[2]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dev_create_student", ROOT / "scripts/dev_create_student.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


@pytest.fixture
async def redis_clean(redis_client: aioredis.Redis) -> aioredis.Redis:
    await redis_client.flushdb()
    return redis_client


async def _owner(db: AsyncSession) -> User:
    owner = User(role=UserRole.OWNER, display_name="Владелец", telegram_id=11)
    db.add(owner)
    await db.commit()
    return owner


async def test_creates_student_profile_and_working_invite(
    db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    owner = await _owner(db_session)
    owner_id = owner.id
    student_id, token = await script.create_test_student(
        db_session, redis_clean, name="  Аня  ", timezone="Asia/Yekaterinburg"
    )
    student = (await db_session.execute(select(User).where(User.id == student_id))).scalar_one()
    assert student.role == UserRole.STUDENT
    assert student.display_name == "Аня"
    assert student.timezone == "Asia/Yekaterinburg"
    assert student.telegram_id is None
    profile = (
        await db_session.execute(select(StudentProfile).where(StudentProfile.user_id == student_id))
    ).scalar_one()
    assert profile.teacher_id == owner_id
    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "invite.created" in actions

    # Приглашение действительно: его можно принять (реальный путь ученика)
    service = AuthService(db_session, SessionStore(redis_clean), RateLimiter(redis_clean))
    result = await service.accept_invite(token, 424242)
    assert result.status == InviteAcceptStatus.LINKED
    assert result.user_id == student_id


async def test_requires_owner(db_session: AsyncSession, redis_clean: aioredis.Redis) -> None:
    with pytest.raises(script.DevScriptError, match="create_owner"):
        await script.create_test_student(db_session, redis_clean, name="Аня", timezone="UTC")


async def test_rejects_bad_input(db_session: AsyncSession, redis_clean: aioredis.Redis) -> None:
    await _owner(db_session)
    with pytest.raises(script.DevScriptError, match="часовой пояс"):
        await script.create_test_student(db_session, redis_clean, name="Аня", timezone="Mars/Base")
    with pytest.raises(script.DevScriptError, match="Имя"):
        await script.create_test_student(db_session, redis_clean, name="   ", timezone="UTC")
    count = (await db_session.execute(select(User).where(User.role == UserRole.STUDENT))).all()
    assert count == []


def test_invite_link_format() -> None:
    assert script.build_invite_link("my_bot", "tok") == "https://t.me/my_bot?start=inv_tok"
    assert script.build_invite_link("@my_bot", "tok") == "https://t.me/my_bot?start=inv_tok"


def test_refuses_in_prod(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    code = script.main(["--bot-username", "my_bot"])
    assert code == script.EXIT_REFUSED
    assert "prod" in capsys.readouterr().out


def test_no_bot_username_and_no_token_gives_clear_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    code = script.main([])
    assert code == script.EXIT_ERROR
    assert "--bot-username" in capsys.readouterr().out
