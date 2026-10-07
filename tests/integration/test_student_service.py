"""Тесты StudentService T2.02 (реальные PostgreSQL и Redis)."""

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.models import AuditLog, StudentProfile, Subject, User
from src.schemas.students import (
    StudentCardManager,
    StudentCardOwner,
    StudentCreate,
    StudentSelfProfile,
    StudentUpdate,
)
from src.services.auth import AuthService
from src.services.students import StudentService, StudentStatus

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
def service(
    db_session: AsyncSession, redis_clean: aioredis.Redis, sessions: SessionStore
) -> StudentService:
    auth = AuthService(db_session, sessions, RateLimiter(redis_clean), BOT_TOKEN)
    return StudentService(db_session, auth)


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
    return await _user(db_session, UserRole.OWNER, "Роман", telegram_id=900_001)


@pytest.fixture
async def manager(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.MANAGER, "Мария", telegram_id=900_002)


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            Subject(code="informatics", name="Информатика"),
            Subject(code="math", name="Математика"),
            Subject(code="retired", name="Старый предмет", is_active=False),
        ]
    )
    await db_session.commit()


async def _audit(db: AsyncSession, action: str) -> list[AuditLog]:
    return list(
        (await db.execute(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)))
        .scalars()
        .all()
    )


# ---------------------------------------------------------------- создание


async def test_owner_creates_student_with_price_subjects_and_defaults(
    service: StudentService, db_session: AsyncSession, owner: User
) -> None:
    card = await service.create_student(
        _actor(owner),
        StudentCreate(
            display_name="Аня",
            school_class=9,
            subject_codes=["math", "informatics"],
            video_url="https://telemost.yandex.ru/j/1",
            teacher_notes="Слабая тема: геометрия",
            lesson_price=1500,
        ),
    )
    assert isinstance(card, StudentCardOwner)
    assert card.lesson_price == 1500
    assert card.teacher_id == owner.id
    assert card.subjects == ["informatics", "math"]
    assert card.timezone == "Europe/Moscow"
    assert card.is_active is True
    assert card.telegram_linked is False
    user = await db_session.get(User, card.user_id)
    assert user is not None
    assert user.role == UserRole.STUDENT
    assert user.telegram_id is None
    assert len(await _audit(db_session, "student.created")) == 1


async def test_manager_creates_student_and_gets_card_without_price(
    service: StudentService, manager: User
) -> None:
    card = await service.create_student(
        _actor(manager), StudentCreate(display_name="Боря", teacher_notes="заметка")
    )
    assert isinstance(card, StudentCardManager)
    assert not isinstance(card, StudentCardOwner)
    assert "lesson_price" not in card.model_dump()
    assert card.teacher_notes == "заметка"
    assert card.teacher_id == manager.id


async def test_manager_cannot_set_price_on_create(
    service: StudentService, db_session: AsyncSession, manager: User
) -> None:
    with pytest.raises(PermissionDeniedError):
        await service.create_student(
            _actor(manager), StudentCreate(display_name="Боря", lesson_price=1000)
        )
    users = (await db_session.execute(select(User).where(User.role == UserRole.STUDENT))).all()
    assert users == []


async def test_create_rejects_unknown_or_inactive_subject(
    service: StudentService, owner: User
) -> None:
    for codes in (["physics"], ["retired"]):
        with pytest.raises(ValidationError) as raised:
            await service.create_student(
                _actor(owner), StudentCreate(display_name="Аня", subject_codes=codes)
            )
        assert raised.value.code == "unknown_subject"


async def test_create_validates_teacher(
    service: StudentService, db_session: AsyncSession, owner: User, manager: User
) -> None:
    other_student = await _user(db_session, UserRole.STUDENT, "Не преподаватель")
    card = await service.create_student(
        _actor(owner), StudentCreate(display_name="Аня", teacher_id=manager.id)
    )
    assert card.teacher_id == manager.id
    for bad in (other_student.id, 999_999_999):
        with pytest.raises(ValidationError) as raised:
            await service.create_student(
                _actor(owner), StudentCreate(display_name="Аня", teacher_id=bad)
            )
        assert raised.value.code == "invalid_teacher"


async def test_student_cannot_manage_students(
    service: StudentService, db_session: AsyncSession
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня")
    actor = _actor(student)
    with pytest.raises(PermissionDeniedError):
        await service.create_student(actor, StudentCreate(display_name="Хакер"))
    with pytest.raises(PermissionDeniedError):
        await service.update_student(actor, student.id, StudentUpdate(display_name="X"))
    with pytest.raises(PermissionDeniedError):
        await service.archive_student(actor, student.id)
    with pytest.raises(PermissionDeniedError):
        await service.restore_student(actor, student.id)
    with pytest.raises(PermissionDeniedError):
        await service.list_students(actor)
    with pytest.raises(PermissionDeniedError):
        await service.unlink_telegram(actor, student.id)


# ---------------------------------------------------------------- изменение


async def test_manager_cannot_change_price(
    service: StudentService, owner: User, manager: User
) -> None:
    card = await service.create_student(
        _actor(owner), StudentCreate(display_name="Аня", lesson_price=1500)
    )
    with pytest.raises(PermissionDeniedError):
        await service.update_student(_actor(manager), card.user_id, StudentUpdate(lesson_price=100))
    after = await service.get_student_card(_actor(owner), card.user_id)
    assert isinstance(after, StudentCardOwner)
    assert after.lesson_price == 1500


async def test_manager_can_update_other_fields_without_seeing_price(
    service: StudentService, owner: User, manager: User
) -> None:
    card = await service.create_student(
        _actor(owner), StudentCreate(display_name="Аня", lesson_price=1500)
    )
    updated = await service.update_student(
        _actor(manager),
        card.user_id,
        StudentUpdate(display_name="Анна", school_class=11, subject_codes=["math"]),
    )
    assert isinstance(updated, StudentCardManager)
    assert "lesson_price" not in updated.model_dump()
    assert (updated.display_name, updated.school_class, updated.subjects) == (
        "Анна",
        11,
        ["math"],
    )
    owner_view = await service.get_student_card(_actor(owner), card.user_id)
    assert isinstance(owner_view, StudentCardOwner)
    assert owner_view.lesson_price == 1500  # менеджер цену не затронул


async def test_owner_price_change_is_audited(
    service: StudentService, db_session: AsyncSession, owner: User
) -> None:
    card = await service.create_student(
        _actor(owner), StudentCreate(display_name="Аня", lesson_price=1500)
    )
    await service.update_student(_actor(owner), card.user_id, StudentUpdate(lesson_price=2000))
    await service.update_student(_actor(owner), card.user_id, StudentUpdate(lesson_price=2000))
    entries = await _audit(db_session, "student.price_changed")
    assert len(entries) == 1  # повтор той же цены в журнал не пишется
    assert entries[0].actor_user_id == owner.id
    assert entries[0].entity_id == card.user_id
    assert entries[0].data == {"old": 1500, "new": 2000}


async def test_update_clears_optional_fields_with_null(
    service: StudentService, owner: User
) -> None:
    card = await service.create_student(
        _actor(owner),
        StudentCreate(display_name="Аня", school_class=9, video_url="https://t.example/1"),
    )
    updated = await service.update_student(
        _actor(owner),
        card.user_id,
        StudentUpdate.model_validate({"school_class": None, "video_url": None}),
    )
    assert updated.school_class is None
    assert updated.video_url is None
    assert updated.display_name == "Аня"


async def test_update_unknown_student_is_404(service: StudentService, owner: User) -> None:
    with pytest.raises(NotFoundError):
        await service.update_student(_actor(owner), 999_999_999, StudentUpdate(display_name="X"))


async def test_staff_user_is_not_a_student(
    service: StudentService, owner: User, manager: User
) -> None:
    with pytest.raises(NotFoundError):
        await service.get_student_card(_actor(owner), manager.id)
    with pytest.raises(NotFoundError):
        await service.archive_student(_actor(owner), manager.id)


# ---------------------------------------------------------------- архив


async def test_archive_removes_sessions_and_keeps_data(
    service: StudentService,
    db_session: AsyncSession,
    sessions: SessionStore,
    owner: User,
) -> None:
    card = await service.create_student(
        _actor(owner), StudentCreate(display_name="Аня", teacher_notes="важно", lesson_price=900)
    )
    session_a, _ = await sessions.create(card.user_id, UserRole.STUDENT)
    session_b, _ = await sessions.create(card.user_id, UserRole.STUDENT)

    archived = await service.archive_student(_actor(owner), card.user_id)

    assert archived.is_active is False
    assert await sessions.get(session_a) is None
    assert await sessions.get(session_b) is None
    profile = await db_session.get(StudentProfile, card.user_id)
    assert profile is not None
    assert profile.teacher_notes == "важно"
    assert profile.lesson_price == 900
    user = await db_session.get(User, card.user_id)
    assert user is not None
    assert user.archived_at is not None
    assert len(await _audit(db_session, "student.archived")) == 1


async def test_archive_twice_and_restore_active_are_business_errors(
    service: StudentService, owner: User
) -> None:
    card = await service.create_student(_actor(owner), StudentCreate(display_name="Аня"))
    with pytest.raises(BusinessRuleError) as not_archived:
        await service.restore_student(_actor(owner), card.user_id)
    assert not_archived.value.code == "student_not_archived"
    await service.archive_student(_actor(owner), card.user_id)
    with pytest.raises(BusinessRuleError) as twice:
        await service.archive_student(_actor(owner), card.user_id)
    assert twice.value.code == "student_already_archived"


async def test_restore_returns_student_to_active_list(
    service: StudentService, db_session: AsyncSession, owner: User
) -> None:
    card = await service.create_student(_actor(owner), StudentCreate(display_name="Аня"))
    await service.archive_student(_actor(owner), card.user_id)
    restored = await service.restore_student(_actor(owner), card.user_id)
    assert restored.is_active is True
    user = await db_session.get(User, card.user_id)
    assert user is not None
    assert user.archived_at is None
    page = await service.list_students(_actor(owner))
    assert [item.user_id for item in page.items] == [card.user_id]
    assert len(await _audit(db_session, "student.restored")) == 1


# ---------------------------------------------------------------- список


async def test_list_filters_search_and_pagination(service: StudentService, owner: User) -> None:
    actor = _actor(owner)
    ids = {}
    for name in ["Алёна", "Борис", "Вера", "Глеб"]:
        ids[name] = (await service.create_student(actor, StudentCreate(display_name=name))).user_id
    await service.archive_student(actor, ids["Глеб"])

    active = await service.list_students(actor)
    assert active.total == 3
    assert [i.display_name for i in active.items] == ["Алёна", "Борис", "Вера"]
    archived = await service.list_students(actor, status=StudentStatus.ARCHIVED)
    assert [i.display_name for i in archived.items] == ["Глеб"]
    assert archived.items[0].is_active is False

    page = await service.list_students(actor, limit=2, offset=1)
    assert (page.total, page.limit, page.offset) == (3, 2, 1)
    assert [i.display_name for i in page.items] == ["Борис", "Вера"]

    found = await service.list_students(actor, q="  БОР ")
    assert [i.display_name for i in found.items] == ["Борис"]
    assert (await service.list_students(actor, q="нет такого")).items == []


async def test_search_treats_like_wildcards_literally(service: StudentService, owner: User) -> None:
    actor = _actor(owner)
    for name in ["100% done", "a_b", "axb"]:
        await service.create_student(actor, StudentCreate(display_name=name))
    percent = await service.list_students(actor, q="%")
    underscore = await service.list_students(actor, q="a_b")
    assert [i.display_name for i in percent.items] == ["100% done"]
    assert [i.display_name for i in underscore.items] == ["a_b"]  # «_» не заменяет «x»


async def test_list_flags_bot_blocked_and_invite_pending(
    service: StudentService, db_session: AsyncSession, owner: User
) -> None:
    actor = _actor(owner)
    linked = await service.create_student(actor, StudentCreate(display_name="Привязан"))
    waiting = await service.create_student(
        actor, StudentCreate(display_name="Ждёт", subject_codes=["math"])
    )
    user = await db_session.get(User, linked.user_id)
    assert user is not None
    user.telegram_id = 777_001
    user.bot_blocked = True
    await db_session.commit()

    items = {i.display_name: i for i in (await service.list_students(actor)).items}
    assert items["Привязан"].telegram_linked is True
    assert items["Привязан"].invite_pending is False
    assert items["Привязан"].bot_blocked is True
    assert items["Ждёт"].telegram_linked is False
    assert items["Ждёт"].invite_pending is True
    assert items["Ждёт"].bot_blocked is False
    assert items["Ждёт"].subjects == ["math"]
    assert waiting.user_id == items["Ждёт"].user_id
    assert "lesson_price" not in items["Ждёт"].model_dump()


async def test_list_rejects_bad_params(service: StudentService, owner: User) -> None:
    for kwargs in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        with pytest.raises(ValidationError):
            await service.list_students(_actor(owner), **kwargs)


# ---------------------------------------------------------------- карточка по ролям


async def test_student_sees_only_own_profile_without_private_fields(
    service: StudentService, owner: User
) -> None:
    card = await service.create_student(
        _actor(owner),
        StudentCreate(
            display_name="Аня",
            teacher_notes="приватно",
            lesson_price=1500,
            board_url="https://board.example/1",
        ),
    )
    other = await service.create_student(_actor(owner), StudentCreate(display_name="Чужой"))
    me = CurrentUser(id=card.user_id, role=UserRole.STUDENT, timezone="Europe/Moscow")

    own = await service.get_student_card(me, card.user_id)
    assert isinstance(own, StudentSelfProfile)
    dumped = own.model_dump()
    assert "teacher_notes" not in dumped
    assert "lesson_price" not in dumped
    assert own.board_url == "https://board.example/1"
    with pytest.raises(NotFoundError):
        await service.get_student_card(me, other.user_id)


async def test_manager_card_hides_price_but_owner_card_has_it(
    service: StudentService, owner: User, manager: User
) -> None:
    card = await service.create_student(
        _actor(owner), StudentCreate(display_name="Аня", lesson_price=1500)
    )
    manager_view = await service.get_student_card(_actor(manager), card.user_id)
    owner_view = await service.get_student_card(_actor(owner), card.user_id)
    assert isinstance(manager_view, StudentCardManager)
    assert not isinstance(manager_view, StudentCardOwner)
    assert "lesson_price" not in manager_view.model_dump()
    assert isinstance(owner_view, StudentCardOwner)
    assert owner_view.lesson_price == 1500


# ---------------------------------------------------------------- Telegram


async def test_unlink_telegram_clears_link_and_sessions(
    service: StudentService,
    db_session: AsyncSession,
    sessions: SessionStore,
    owner: User,
) -> None:
    card = await service.create_student(_actor(owner), StudentCreate(display_name="Аня"))
    user = await db_session.get(User, card.user_id)
    assert user is not None
    user.telegram_id = 777_002
    await db_session.commit()
    session_id, _ = await sessions.create(card.user_id, UserRole.STUDENT)

    await service.unlink_telegram(_actor(owner), card.user_id)

    await db_session.refresh(user)
    assert user.telegram_id is None
    assert await sessions.get(session_id) is None
    assert len(await _audit(db_session, "telegram.unlinked")) == 1
    with pytest.raises(BusinessRuleError):  # повторно: уже не привязан
        await service.unlink_telegram(_actor(owner), card.user_id)
