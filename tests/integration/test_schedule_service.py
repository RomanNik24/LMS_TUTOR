"""ScheduleService.create_lesson (T3.04, US-02): права, участники, пересечения (PostgreSQL)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import LessonStatus, UserRole
from src.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.db.models import AuditLog, Lesson, LessonParticipant, Subject, User
from src.schemas.schedule import LessonCreate
from src.services.schedule import ScheduleService

pytestmark = pytest.mark.security

START = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


@pytest.fixture
def service(db_session: AsyncSession) -> ScheduleService:
    return ScheduleService(db_session)


async def _user(db: AsyncSession, role: UserRole, name: str, *, active: bool = True) -> User:
    user = User(role=role, display_name=name, is_active=active)
    db.add(user)
    await db.commit()
    return user


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман")


@pytest.fixture
async def manager(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.MANAGER, "Мария")


@pytest.fixture
async def anya(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Аня")


@pytest.fixture
async def boris(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Борис")


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add_all(
        [Subject(code="informatics", name="Информатика"), Subject(code="math", name="Математика")]
    )
    await db_session.commit()


def make(student_ids: list[int], start: datetime = START, minutes: int = 60, **extra: object):
    return LessonCreate.model_validate(
        {
            "subject_code": "informatics",
            "student_ids": student_ids,
            "start_at": start,
            "end_at": start + timedelta(minutes=minutes),
            **extra,
        }
    )


async def _count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# ---------------------------------------------------------------- создание


async def test_owner_creates_single_lesson(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_lesson(
        _actor(owner),
        make(
            [anya.id],
            topic="Графы",
            video_url_override="https://telemost.yandex.ru/j/1",
            board_url_override="https://miro.com/b/1",
        ),
    )
    assert item.teacher_id == owner.id
    assert item.subject_code == "informatics"
    assert item.status == LessonStatus.SCHEDULED
    assert item.is_detached is False
    assert item.topic == "Графы"
    assert [p.student_id for p in item.participants] == [anya.id]
    assert item.participants[0].attendance == "pending"
    row = (await db_session.execute(select(LessonParticipant))).scalar_one()
    assert (row.is_billable, row.price_snapshot) == (False, None)
    audit = await db_session.execute(select(AuditLog).where(AuditLog.action == "lesson.created"))
    assert audit.scalar_one().entity_id == item.id


async def test_group_lesson_with_several_participants(
    service: ScheduleService, db_session: AsyncSession, manager: User, anya: User, boris: User
) -> None:
    item = await service.create_lesson(_actor(manager), make([anya.id, boris.id]))
    assert {p.student_id for p in item.participants} == {anya.id, boris.id}
    assert await _count(db_session, LessonParticipant) == 2


async def test_manager_can_create_lesson_for_another_teacher(
    service: ScheduleService, owner: User, manager: User, anya: User
) -> None:
    item = await service.create_lesson(_actor(manager), make([anya.id], teacher_id=owner.id))
    assert item.teacher_id == owner.id


# ---------------------------------------------------------------- пересечения (US-02)


async def test_overlap_of_same_teacher_is_conflict(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    await service.create_lesson(_actor(owner), make([anya.id]))
    with pytest.raises(ConflictError) as raised:
        await service.create_lesson(_actor(owner), make([boris.id], START + timedelta(minutes=30)))
    assert raised.value.code == "lesson_overlap"
    assert raised.value.http_status == 409
    assert await _count(db_session, Lesson) == 1
    assert await _count(db_session, LessonParticipant) == 1


async def test_back_to_back_lessons_are_allowed(
    service: ScheduleService, owner: User, anya: User
) -> None:
    await service.create_lesson(_actor(owner), make([anya.id]))
    await service.create_lesson(_actor(owner), make([anya.id], START + timedelta(hours=1)))


async def test_other_teacher_may_use_same_time(
    service: ScheduleService, owner: User, manager: User, anya: User, boris: User
) -> None:
    await service.create_lesson(_actor(owner), make([anya.id]))
    await service.create_lesson(_actor(manager), make([boris.id]))


async def test_service_is_usable_after_overlap_error(
    service: ScheduleService, owner: User, anya: User
) -> None:
    await service.create_lesson(_actor(owner), make([anya.id]))
    with pytest.raises(ConflictError):
        await service.create_lesson(_actor(owner), make([anya.id]))
    later = await service.create_lesson(_actor(owner), make([anya.id], START + timedelta(days=1)))
    assert later.id


# ---------------------------------------------------------------- участники и входные данные


async def test_archived_student_cannot_be_added(
    service: ScheduleService, db_session: AsyncSession, owner: User
) -> None:
    archived = await _user(db_session, UserRole.STUDENT, "Бывший", active=False)
    with pytest.raises(BusinessRuleError) as raised:
        await service.create_lesson(_actor(owner), make([archived.id]))
    assert raised.value.code == "student_archived"
    assert await _count(db_session, Lesson) == 0


async def test_missing_or_non_student_participant_is_404(
    service: ScheduleService, owner: User, manager: User
) -> None:
    for student_id in (999_999_999, manager.id):
        with pytest.raises(NotFoundError):
            await service.create_lesson(_actor(owner), make([student_id]))


async def test_unknown_subject_and_invalid_teacher(
    service: ScheduleService, owner: User, anya: User, boris: User
) -> None:
    with pytest.raises(ValidationError) as unknown:
        await service.create_lesson(_actor(owner), make([anya.id], subject_code="physics"))
    assert unknown.value.code == "unknown_subject"
    with pytest.raises(ValidationError) as teacher:
        await service.create_lesson(_actor(owner), make([anya.id], teacher_id=boris.id))
    assert teacher.value.code == "invalid_teacher"


async def test_student_cannot_create_lesson(
    service: ScheduleService, db_session: AsyncSession, anya: User
) -> None:
    with pytest.raises(PermissionDeniedError):
        await service.create_lesson(_actor(anya), make([anya.id]))
    assert await _count(db_session, Lesson) == 0
