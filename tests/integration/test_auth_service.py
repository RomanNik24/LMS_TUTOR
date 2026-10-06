"""Тесты AuthService T1.09 по US-01 (реальные PostgreSQL и Redis)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as aioredis
import time_machine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import AuthTokenPurpose, UserRole
from src.core.exceptions import (
    AppError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from src.core.rate_limit import RateLimiter
from src.core.security import hash_token
from src.core.session_store import SessionStore
from src.db.models import AuditLog, AuthToken, StudentProfile, User
from src.services.auth import AuthService, InviteAcceptStatus

pytestmark = pytest.mark.security

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
BOT_TOKEN = "123:TEST"  # noqa: S105 - тестовый токен


@pytest.fixture
async def redis_clean(redis_client: aioredis.Redis) -> aioredis.Redis:
    await redis_client.flushdb()
    return redis_client


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def service(db_session: AsyncSession, redis_clean: aioredis.Redis) -> AuthService:
    return AuthService(db_session, SessionStore(redis_clean), RateLimiter(redis_clean), BOT_TOKEN)


async def _make(
    db: AsyncSession,
    role: UserRole,
    name: str,
    *,
    telegram_id: int | None = None,
    active: bool = True,
) -> User:
    user = User(role=role, display_name=name, telegram_id=telegram_id, is_active=active)
    db.add(user)
    await db.commit()
    return user


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


async def _student(
    db: AsyncSession,
    owner: User,
    name: str = "Аня",
    *,
    telegram_id: int | None = None,
    active: bool = True,
) -> User:
    student = await _make(db, UserRole.STUDENT, name, telegram_id=telegram_id, active=active)
    db.add(StudentProfile(user_id=student.id, teacher_id=owner.id))
    await db.commit()
    return student


async def _audit_actions(db: AsyncSession) -> list[str]:
    rows = await db.execute(select(AuditLog.action).order_by(AuditLog.id))
    return [r[0] for r in rows]


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _make(db_session, UserRole.OWNER, "Владелец", telegram_id=1)


# ---------------------------------------------------------------- create / revoke


async def test_create_invite_stores_only_hash_and_ttl_7_days(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner)
    issued = await service.create_invite(_actor(owner), student.id)
    assert issued.expires_at == NOW + timedelta(days=7)
    row = (await db_session.execute(select(AuthToken))).scalar_one()
    assert row.token_hash == hash_token(issued.token)
    assert issued.token not in row.token_hash
    assert row.purpose == AuthTokenPurpose.INVITE
    assert row.created_by == owner.id
    assert "invite.created" in await _audit_actions(db_session)


async def test_new_invite_revokes_previous(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner)
    first = await service.create_invite(_actor(owner), student.id)
    second = await service.create_invite(_actor(owner), student.id)
    with pytest.raises(NotFoundError) as exc:
        await service.accept_invite(first.token, 500)
    assert exc.value.code == "invite_invalid"
    result = await service.accept_invite(second.token, 500)
    assert result.status == InviteAcceptStatus.LINKED


async def test_revoke_invite(service: AuthService, db_session: AsyncSession, owner: User) -> None:
    student = await _student(db_session, owner)
    actor, student_id = _actor(owner), student.id
    issued = await service.create_invite(actor, student_id)
    await service.revoke_invite(actor, student_id)
    with pytest.raises(NotFoundError):
        await service.accept_invite(issued.token, 500)
    with pytest.raises(NotFoundError) as exc:
        await service.revoke_invite(actor, student_id)
    assert exc.value.code == "invite_not_found"
    assert "invite.revoked" in await _audit_actions(db_session)


async def test_student_cannot_create_invite(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner)
    with pytest.raises(PermissionDeniedError):
        await service.create_invite(_actor(student), student.id)


async def test_manager_cannot_invite_staff_but_owner_can(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    manager = await _make(db_session, UserRole.MANAGER, "Менеджер")
    with pytest.raises(PermissionDeniedError):
        await service.create_invite(_actor(manager), manager.id)
    issued = await service.create_invite(_actor(owner), manager.id)
    assert issued.token


async def test_invite_for_archived_or_missing_user(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    archived = await _student(db_session, owner, "Архив", active=False)
    with pytest.raises(BusinessRuleError) as exc:
        await service.create_invite(_actor(owner), archived.id)
    assert exc.value.code == "user_archived"
    with pytest.raises(NotFoundError):
        await service.create_invite(_actor(owner), 987_654_321)


# ---------------------------------------------------------------- accept


async def test_accept_invite_links_telegram_and_marks_used(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner, "Аня")
    issued = await service.create_invite(_actor(owner), student.id)
    result = await service.accept_invite(issued.token, 777, "anya")
    assert result.status == InviteAcceptStatus.LINKED
    assert (result.user_id, result.role, result.display_name) == (
        student.id,
        UserRole.STUDENT,
        "Аня",
    )
    await db_session.refresh(student)
    assert student.telegram_id == 777
    assert student.telegram_username == "anya"
    row = (await db_session.execute(select(AuthToken))).scalar_one()
    assert row.used_at == NOW
    assert "invite.accepted" in await _audit_actions(db_session)


async def test_invite_used_twice_is_rejected(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner)
    issued = await service.create_invite(_actor(owner), student.id)
    await service.accept_invite(issued.token, 777)
    with pytest.raises(ConflictError) as exc:
        await service.accept_invite(issued.token, 888)
    assert exc.value.code == "invite_already_used"


async def test_invite_expired_after_7_days(
    service: AuthService, db_session: AsyncSession, owner: User, _frozen: None
) -> None:
    student = await _student(db_session, owner)
    issued = await service.create_invite(_actor(owner), student.id)
    with time_machine.travel(NOW + timedelta(days=7, seconds=1), tick=False):
        with pytest.raises(NotFoundError) as exc:
            await service.accept_invite(issued.token, 777)
    assert exc.value.code == "invite_invalid"
    with time_machine.travel(NOW + timedelta(days=6, hours=23), tick=False):
        result = await service.accept_invite(issued.token, 777)
    assert result.status == InviteAcceptStatus.LINKED


async def test_unknown_token_is_invalid(service: AuthService) -> None:
    with pytest.raises(NotFoundError) as exc:
        await service.accept_invite("no-such-token", 777)
    assert exc.value.code == "invite_invalid"


async def test_web_login_token_is_not_accepted_as_invite(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    issued = await service.create_web_login_link(_actor(owner))
    with pytest.raises(NotFoundError):
        await service.accept_invite(issued.token, 777)


async def test_telegram_already_linked_to_another_profile(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    await _student(db_session, owner, "Первый", telegram_id=777)
    second = await _student(db_session, owner, "Второй")
    issued = await service.create_invite(_actor(owner), second.id)
    with pytest.raises(ConflictError) as exc:
        await service.accept_invite(issued.token, 777)
    assert exc.value.code == "telegram_already_linked"
    # Токен не погашен: приглашение ещё можно принять другим аккаунтом.
    result = await service.accept_invite(issued.token, 778)
    assert result.status == InviteAcceptStatus.LINKED


async def test_archived_target_makes_invite_invalid(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner)
    issued = await service.create_invite(_actor(owner), student.id)
    student.is_active = False
    await db_session.commit()
    with pytest.raises(NotFoundError):
        await service.accept_invite(issued.token, 777)


# ---------------------------------------------------------------- relink


async def test_relink_requires_confirmation(
    service: AuthService, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student = await _student(db_session, owner, telegram_id=111)
    old_session, _ = await SessionStore(redis_clean).create(student.id, student.role)
    issued = await service.create_invite(_actor(owner), student.id)

    pending = await service.accept_invite(issued.token, 222)
    assert pending.status == InviteAcceptStatus.RELINK_REQUIRED
    await db_session.refresh(student)
    assert student.telegram_id == 111  # пока ничего не изменилось
    assert await SessionStore(redis_clean).get(old_session) is not None

    done = await service.confirm_relink(issued.token, 222, "new")
    assert done.status == InviteAcceptStatus.LINKED
    await db_session.refresh(student)
    assert student.telegram_id == 222
    assert await SessionStore(redis_clean).get(old_session) is None  # старые сессии сняты
    assert "telegram.relinked" in await _audit_actions(db_session)
    with pytest.raises(ConflictError):  # токен погашен
        await service.confirm_relink(issued.token, 222)


async def test_relink_to_telegram_of_other_profile_is_rejected(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner, telegram_id=111)
    await _student(db_session, owner, "Другой", telegram_id=222)
    issued = await service.create_invite(_actor(owner), student.id)
    with pytest.raises(ConflictError) as exc:
        await service.confirm_relink(issued.token, 222)
    assert exc.value.code == "telegram_already_linked"


async def test_same_telegram_accepting_again_is_idempotent_link(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner, telegram_id=111)
    issued = await service.create_invite(_actor(owner), student.id)
    result = await service.accept_invite(issued.token, 111)
    assert result.status == InviteAcceptStatus.LINKED


# ---------------------------------------------------------------- failed attempts


async def test_failed_attempts_limit_5_per_10_minutes(
    service: AuthService, redis_clean: aioredis.Redis
) -> None:
    for _ in range(5):
        with pytest.raises(NotFoundError):
            await service.accept_invite("bad", 4242)
    with pytest.raises(AppError) as exc:
        await service.accept_invite("bad", 4242)
    assert exc.value.http_status == 429
    assert exc.value.code == "rate_limited"
    # Другой telegram_id не затронут.
    with pytest.raises(NotFoundError):
        await service.accept_invite("bad", 4243)
    # Окно неудач ограничено 10 минутами (TTL счётчика в Redis).
    ttl = await redis_clean.ttl("rate:invite_fail:4242")
    assert 0 < ttl <= 600


async def test_blocked_user_cannot_use_valid_invite(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner)
    issued = await service.create_invite(_actor(owner), student.id)
    for _ in range(5):
        with pytest.raises(NotFoundError):
            await service.accept_invite("bad", 31337)
    with pytest.raises(AppError) as exc:
        await service.accept_invite(issued.token, 31337)
    assert exc.value.http_status == 429


# ---------------------------------------------------------------- web login


async def test_web_login_is_one_time_with_10_minute_ttl(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    issued = await service.create_web_login_link(_actor(owner))
    assert issued.expires_at == NOW + timedelta(minutes=10)
    user = await service.consume_web_login(issued.token)
    assert (user.id, user.role) == (owner.id, UserRole.OWNER)
    with pytest.raises(ConflictError) as exc:
        await service.consume_web_login(issued.token)
    assert exc.value.code == "invite_already_used"


async def test_web_login_expired(service: AuthService, owner: User, _frozen: None) -> None:
    issued = await service.create_web_login_link(_actor(owner))
    with time_machine.travel(NOW + timedelta(minutes=10, seconds=1), tick=False):
        with pytest.raises(NotFoundError) as exc:
            await service.consume_web_login(issued.token)
    assert exc.value.code == "login_link_invalid"


async def test_web_login_unknown_and_invite_token(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    with pytest.raises(NotFoundError):
        await service.consume_web_login("nope")
    student = await _student(db_session, owner)
    invite = await service.create_invite(_actor(owner), student.id)
    with pytest.raises(NotFoundError):
        await service.consume_web_login(invite.token)


async def test_web_login_for_archived_user_is_rejected(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner, telegram_id=5)
    issued = await service.create_web_login_link(_actor(student))
    student.is_active = False
    await db_session.commit()
    with pytest.raises(NotFoundError):
        await service.consume_web_login(issued.token)


async def test_web_login_link_for_archived_actor_is_denied(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner, active=False)
    with pytest.raises(PermissionDeniedError):
        await service.create_web_login_link(_actor(student))


# ---------------------------------------------------------------- unlink / sessions


async def test_unlink_telegram_by_staff_clears_sessions(
    service: AuthService, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student = await _student(db_session, owner, telegram_id=900)
    session_id, _ = await SessionStore(redis_clean).create(student.id, student.role)
    await service.unlink_telegram(_actor(owner), student.id)
    await db_session.refresh(student)
    assert student.telegram_id is None
    assert await SessionStore(redis_clean).get(session_id) is None
    assert "telegram.unlinked" in await _audit_actions(db_session)
    with pytest.raises(BusinessRuleError) as exc:
        await service.unlink_telegram(_actor(owner), student.id)
    assert exc.value.code == "telegram_not_linked"


async def test_student_can_unlink_self_but_not_others(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    mine = await _student(db_session, owner, "Я", telegram_id=901)
    other = await _student(db_session, owner, "Чужой", telegram_id=902)
    with pytest.raises(PermissionDeniedError):
        await service.unlink_telegram(_actor(mine), other.id)
    await service.unlink_telegram(_actor(mine), mine.id)


async def test_manager_cannot_unlink_owner(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    manager = await _make(db_session, UserRole.MANAGER, "М", telegram_id=3)
    with pytest.raises(PermissionDeniedError):
        await service.unlink_telegram(_actor(manager), owner.id)


async def test_create_and_delete_sessions(
    service: AuthService, db_session: AsyncSession, owner: User
) -> None:
    student = await _student(db_session, owner)
    session_id, ttl = await service.create_session(_actor(student))
    assert ttl == 30 * 24 * 3600
    with pytest.raises(PermissionDeniedError):
        await service.delete_sessions(_actor(student), owner.id)
    assert await service.delete_sessions(_actor(owner), student.id) == 1
    assert session_id


def test_validate_init_data_uses_bot_token(service: AuthService) -> None:
    with pytest.raises(AppError) as exc:
        service.validate_init_data("auth_date=1&hash=abc")
    assert exc.value.http_status == 401


# ---------------------------------------------------------------- owner


async def test_ensure_owner_is_idempotent(service: AuthService, db_session: AsyncSession) -> None:
    first = await service.ensure_owner(555_000)
    second = await service.ensure_owner(555_000)
    assert first.id == second.id
    assert first.role == UserRole.OWNER
    assert first.telegram_id == 555_000
    count = await db_session.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.OWNER)
    )
    assert count == 1


async def test_ensure_owner_does_not_replace_existing_owner(
    service: AuthService, owner: User
) -> None:
    again = await service.ensure_owner(999_999)
    assert again.id == owner.id


async def test_ensure_owner_conflicts_with_foreign_telegram_id(
    service: AuthService, db_session: AsyncSession
) -> None:
    await _make(db_session, UserRole.MANAGER, "Занят", telegram_id=42)
    with pytest.raises(ConflictError) as exc:
        await service.ensure_owner(42)
    assert exc.value.code == "owner_telegram_id_taken"
