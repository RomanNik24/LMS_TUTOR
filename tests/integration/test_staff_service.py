"""Тесты StaffService T2.03: только владелец, смена роли, последний владелец (PG и Redis)."""

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import BusinessRuleError, NotFoundError, PermissionDeniedError
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.models import AuditLog, AuthToken, User
from src.schemas.staff import StaffCreate, StaffUpdate
from src.services.auth import AuthService, InviteAcceptStatus
from src.services.staff import StaffService

pytestmark = pytest.mark.security

BOT_TOKEN = "123:TEST"  # noqa: S105 - тестовый токен


@pytest.fixture
async def redis_clean(redis_client: aioredis.Redis) -> aioredis.Redis:
    await redis_client.flushdb()
    return redis_client


@pytest.fixture
def sessions(redis_clean: aioredis.Redis) -> SessionStore:
    return SessionStore(redis_clean)


@pytest.fixture
def auth(
    db_session: AsyncSession, redis_clean: aioredis.Redis, sessions: SessionStore
) -> AuthService:
    return AuthService(db_session, sessions, RateLimiter(redis_clean), BOT_TOKEN)


@pytest.fixture
def service(db_session: AsyncSession, auth: AuthService) -> StaffService:
    return StaffService(db_session, auth)


async def _user(
    db: AsyncSession, role: UserRole, name: str, *, telegram_id: int | None = None
) -> User:
    user = User(role=role, display_name=name, telegram_id=telegram_id)
    db.add(user)
    await db.commit()
    return user


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман", telegram_id=910_001)


@pytest.fixture
async def manager(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.MANAGER, "Мария", telegram_id=910_002)


async def _audit(db: AsyncSession, action: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
    return list((await db.execute(stmt)).scalars().all())


# ---------------------------------------------------------------- только владелец


async def test_manager_and_student_get_403_on_every_operation(
    service: StaffService, db_session: AsyncSession, owner: User, manager: User
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня")
    for actor in (_actor(manager), _actor(student)):
        with pytest.raises(PermissionDeniedError):
            await service.create_staff(actor, StaffCreate(display_name="Новый"))
        with pytest.raises(PermissionDeniedError):
            await service.list_staff(actor)
        with pytest.raises(PermissionDeniedError):
            await service.update_staff(actor, manager.id, StaffUpdate(display_name="X"))
        with pytest.raises(PermissionDeniedError):
            await service.change_role(actor, manager.id, UserRole.OWNER)
        with pytest.raises(PermissionDeniedError):
            await service.invite_staff(actor, manager.id)
        with pytest.raises(PermissionDeniedError):
            await service.archive_staff(actor, manager.id)
    refreshed = await db_session.get(User, manager.id)
    assert refreshed is not None
    assert refreshed.role == UserRole.MANAGER
    assert refreshed.is_active is True


# ---------------------------------------------------------------- создание и список


async def test_owner_creates_manager_and_owner(
    service: StaffService, db_session: AsyncSession, owner: User
) -> None:
    created = await service.create_staff(
        _actor(owner), StaffCreate(display_name="Мария", timezone="Asia/Yekaterinburg")
    )
    assert created.role == UserRole.MANAGER
    assert created.timezone == "Asia/Yekaterinburg"
    assert created.is_active is True
    assert created.telegram_linked is False
    assert created.invite_pending is True
    second_owner = await service.create_staff(
        _actor(owner), StaffCreate(display_name="Совладелец", role=UserRole.OWNER)
    )
    assert second_owner.role == UserRole.OWNER
    assert len(await _audit(db_session, "staff.created")) == 2


async def test_list_staff_excludes_students_and_archived_by_default(
    service: StaffService, db_session: AsyncSession, owner: User, manager: User
) -> None:
    await _user(db_session, UserRole.STUDENT, "Ученик")
    archived = await service.create_staff(_actor(owner), StaffCreate(display_name="Архивный"))
    await service.archive_staff(_actor(owner), archived.user_id)

    active = await service.list_staff(_actor(owner))
    assert {i.display_name for i in active} == {"Роман", "Мария"}
    everyone = await service.list_staff(_actor(owner), include_archived=True)
    assert {i.display_name for i in everyone} == {"Роман", "Мария", "Архивный"}
    assert all(i.role in (UserRole.OWNER, UserRole.MANAGER) for i in everyone)


# ---------------------------------------------------------------- роль и имя


async def test_change_role_is_audited_and_removes_sessions(
    service: StaffService,
    db_session: AsyncSession,
    sessions: SessionStore,
    owner: User,
    manager: User,
) -> None:
    session_id, _ = await sessions.create(manager.id, UserRole.MANAGER)

    item = await service.change_role(_actor(owner), manager.id, UserRole.OWNER)

    assert item.role == UserRole.OWNER
    assert await sessions.get(session_id) is None
    entries = await _audit(db_session, "staff.role_changed")
    assert len(entries) == 1
    assert entries[0].actor_user_id == owner.id
    assert entries[0].entity_id == manager.id
    assert entries[0].data == {"old": "manager", "new": "owner"}


async def test_same_role_and_rename_do_not_touch_sessions_or_audit(
    service: StaffService,
    db_session: AsyncSession,
    sessions: SessionStore,
    owner: User,
    manager: User,
) -> None:
    session_id, _ = await sessions.create(manager.id, UserRole.MANAGER)
    item = await service.update_staff(
        _actor(owner),
        manager.id,
        StaffUpdate.model_validate({"display_name": "Мария П.", "role": UserRole.MANAGER}),
    )
    assert item.display_name == "Мария П."
    assert item.role == UserRole.MANAGER
    assert await sessions.get(session_id) is not None
    assert await _audit(db_session, "staff.role_changed") == []


async def test_student_is_not_staff(
    service: StaffService, db_session: AsyncSession, owner: User
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня")
    with pytest.raises(NotFoundError):
        await service.update_staff(_actor(owner), student.id, StaffUpdate(display_name="X"))
    with pytest.raises(NotFoundError):
        await service.invite_staff(_actor(owner), student.id)
    with pytest.raises(NotFoundError):
        await service.archive_staff(_actor(owner), student.id)
    with pytest.raises(NotFoundError):
        await service.change_role(_actor(owner), 999_999_999, UserRole.MANAGER)


# ---------------------------------------------------------------- последний владелец


async def test_last_owner_cannot_be_demoted(
    service: StaffService, db_session: AsyncSession, owner: User, manager: User
) -> None:
    with pytest.raises(BusinessRuleError) as raised:
        await service.change_role(_actor(owner), owner.id, UserRole.MANAGER)
    assert raised.value.code == "last_owner"
    refreshed = await db_session.get(User, owner.id)
    assert refreshed is not None
    assert refreshed.role == UserRole.OWNER
    assert await _audit(db_session, "staff.role_changed") == []


async def test_last_owner_cannot_be_archived(
    service: StaffService, db_session: AsyncSession, owner: User
) -> None:
    with pytest.raises(BusinessRuleError) as raised:
        await service.archive_staff(_actor(owner), owner.id)
    assert raised.value.code == "last_owner"
    refreshed = await db_session.get(User, owner.id)
    assert refreshed is not None
    assert refreshed.is_active is True


async def test_with_two_owners_one_can_go_but_not_the_remaining_one(
    service: StaffService, db_session: AsyncSession, owner: User
) -> None:
    second = await service.create_staff(
        _actor(owner), StaffCreate(display_name="Совладелец", role=UserRole.OWNER)
    )
    await service.change_role(_actor(owner), second.user_id, UserRole.MANAGER)  # владельцев снова 1
    with pytest.raises(BusinessRuleError):
        await service.archive_staff(_actor(owner), owner.id)

    await service.change_role(_actor(owner), second.user_id, UserRole.OWNER)  # снова двое
    archived = await service.archive_staff(_actor(owner), second.user_id)
    assert archived.is_active is False
    with pytest.raises(BusinessRuleError):  # остался один активный владелец
        await service.change_role(_actor(owner), owner.id, UserRole.MANAGER)


async def test_archived_owner_does_not_count_as_active_owner(
    service: StaffService, db_session: AsyncSession, owner: User
) -> None:
    archived_owner = await _user(db_session, UserRole.OWNER, "Бывший владелец")
    archived_owner.is_active = False
    await db_session.commit()
    with pytest.raises(BusinessRuleError):  # единственный активный — это owner
        await service.archive_staff(_actor(owner), owner.id)


# ---------------------------------------------------------------- приглашение и архив


async def test_invite_staff_can_be_accepted(
    service: StaffService, auth: AuthService, db_session: AsyncSession, owner: User
) -> None:
    created = await service.create_staff(_actor(owner), StaffCreate(display_name="Мария"))
    issued = await service.invite_staff(_actor(owner), created.user_id)

    result = await auth.accept_invite(issued.token, 910_777)

    assert result.status == InviteAcceptStatus.LINKED
    assert result.role == UserRole.MANAGER
    user = await db_session.get(User, created.user_id)
    assert user is not None
    assert user.telegram_id == 910_777
    tokens = (await db_session.execute(select(AuthToken).where(AuthToken.user_id == user.id))).all()
    assert len(tokens) == 1
    staff = {i.user_id: i for i in await service.list_staff(_actor(owner))}
    assert staff[created.user_id].telegram_linked is True
    assert staff[created.user_id].invite_pending is False


async def test_archive_removes_sessions_and_blocks_invites(
    service: StaffService,
    db_session: AsyncSession,
    sessions: SessionStore,
    owner: User,
    manager: User,
) -> None:
    session_id, _ = await sessions.create(manager.id, UserRole.MANAGER)

    item = await service.archive_staff(_actor(owner), manager.id)

    assert item.is_active is False
    assert await sessions.get(session_id) is None
    user = await db_session.get(User, manager.id)
    assert user is not None
    assert user.archived_at is not None
    assert len(await _audit(db_session, "staff.archived")) == 1
    with pytest.raises(BusinessRuleError):
        await service.archive_staff(_actor(owner), manager.id)
    with pytest.raises(BusinessRuleError):
        await service.invite_staff(_actor(owner), manager.id)
