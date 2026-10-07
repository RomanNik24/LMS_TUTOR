"""ScheduleService (T3.04–T3.05, US-02): создание, перенос, отмена, отметка проведения."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import AttendanceStatus, LessonStatus, UserRole
from src.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.db.models import AuditLog, Lesson, LessonParticipant, StudentProfile, Subject, User
from src.schemas.schedule import LessonCancel, LessonComplete, LessonCreate, LessonReschedule
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


async def _student(db: AsyncSession, name: str, teacher: User, price: int) -> User:
    user = await _user(db, UserRole.STUDENT, name)
    db.add(StudentProfile(user_id=user.id, teacher_id=teacher.id, lesson_price=price))
    await db.commit()
    return user


@pytest.fixture
async def anya(db_session: AsyncSession, owner: User) -> User:
    return await _student(db_session, "Аня", owner, 1500)


@pytest.fixture
async def boris(db_session: AsyncSession, owner: User) -> User:
    return await _student(db_session, "Борис", owner, 2000)


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


# ---------------------------------------------------------------- перенос (T3.05)


async def _lesson(
    service: ScheduleService, owner: User, ids: list[int], start: datetime = START
) -> int:
    return (await service.create_lesson(_actor(owner), make(ids, start))).id


def _move(start: datetime, minutes: int = 60) -> LessonReschedule:
    return LessonReschedule(start_at=start, end_at=start + timedelta(minutes=minutes))


async def test_reschedule_changes_time_detaches_and_audits(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id])
    new_start = START + timedelta(days=2)
    item = await service.reschedule_lesson(_actor(owner), lesson_id, _move(new_start))
    assert (item.start_at, item.is_detached) == (new_start, True)
    entry = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "lesson.rescheduled"))
    ).scalar_one()
    assert entry.data["old"]["start_at"] == START.isoformat()
    assert entry.data["new"]["start_at"] == new_start.isoformat()


async def test_reschedule_into_overlap_is_conflict_and_changes_nothing(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    first = await _lesson(service, owner, [anya.id])
    await _lesson(service, owner, [anya.id], start=START + timedelta(hours=3))
    with pytest.raises(ConflictError) as raised:
        await service.reschedule_lesson(
            _actor(owner), first, _move(START + timedelta(hours=3, minutes=30))
        )
    assert raised.value.code == "lesson_overlap"
    db_session.expire_all()
    stored = await db_session.get(Lesson, first)
    assert stored is not None
    assert (stored.start_at, stored.is_detached) == (START, False)


async def test_reschedule_rules(
    service: ScheduleService, owner: User, anya: User, boris: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id])
    with pytest.raises(NotFoundError) as missing:
        await service.reschedule_lesson(_actor(owner), 999_999_999, _move(START))
    assert missing.value.code == "lesson_not_found"
    with pytest.raises(PermissionDeniedError):
        await service.reschedule_lesson(_actor(anya), lesson_id, _move(START))
    await service.cancel_lesson(_actor(owner), lesson_id, LessonCancel())
    with pytest.raises(BusinessRuleError) as cancelled:
        await service.reschedule_lesson(_actor(owner), lesson_id, _move(START))
    assert cancelled.value.code == "lesson_not_scheduled"


# ---------------------------------------------------------------- отмена (T3.05)


async def test_cancel_marks_lesson_and_participants(
    service: ScheduleService, db_session: AsyncSession, manager: User, owner: User, anya: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id])
    item = await service.cancel_lesson(
        _actor(manager), lesson_id, LessonCancel(reason="  Болезнь  ")
    )
    assert item.status == LessonStatus.CANCELLED
    assert item.cancel_reason == "Болезнь"
    assert item.cancelled_at is not None
    assert item.participants[0].attendance == AttendanceStatus.CANCELLED
    row = (await db_session.execute(select(LessonParticipant))).scalar_one()
    assert (row.is_billable, row.price_snapshot) == (False, None)
    lesson = await db_session.get(Lesson, lesson_id)
    assert lesson is not None
    assert lesson.cancelled_by == manager.id


async def test_cancel_with_billable_student_fixes_price(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id, boris.id])
    await service.cancel_lesson(
        _actor(owner), lesson_id, LessonCancel(billable_student_ids=[boris.id])
    )
    rows = {
        r.student_id: r for r in (await db_session.execute(select(LessonParticipant))).scalars()
    }
    assert (rows[boris.id].is_billable, rows[boris.id].price_snapshot) == (True, 2000)
    assert (rows[anya.id].is_billable, rows[anya.id].price_snapshot) == (False, None)


async def test_cancel_rules(service: ScheduleService, owner: User, anya: User, boris: User) -> None:
    lesson_id = await _lesson(service, owner, [anya.id])
    with pytest.raises(BusinessRuleError) as stranger:
        await service.cancel_lesson(
            _actor(owner), lesson_id, LessonCancel(billable_student_ids=[boris.id])
        )
    assert stranger.value.code == "not_participant"
    with pytest.raises(PermissionDeniedError):
        await service.cancel_lesson(_actor(anya), lesson_id, LessonCancel())
    await service.cancel_lesson(_actor(owner), lesson_id, LessonCancel())
    with pytest.raises(BusinessRuleError) as twice:
        await service.cancel_lesson(_actor(owner), lesson_id, LessonCancel())
    assert twice.value.code == "lesson_not_scheduled"


async def test_cancelled_lesson_frees_the_time_slot(
    service: ScheduleService, owner: User, anya: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id])
    await service.cancel_lesson(_actor(owner), lesson_id, LessonCancel())
    await _lesson(service, owner, [anya.id])


# ---------------------------------------------------------------- проведение (T3.05)


def _complete(*marks: dict[str, object]) -> LessonComplete:
    return LessonComplete.model_validate({"marks": list(marks)})


async def _rows(db: AsyncSession) -> dict[int, LessonParticipant]:
    stmt = select(LessonParticipant).execution_options(populate_existing=True)
    return {r.student_id: r for r in (await db.execute(stmt)).scalars()}


async def test_complete_defaults_and_price_snapshot(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id, boris.id])
    item = await service.complete_lesson(
        _actor(owner),
        lesson_id,
        _complete(
            {"student_id": anya.id, "attendance": "attended"},
            {"student_id": boris.id, "attendance": "no_show"},
        ),
    )
    assert item.status == LessonStatus.COMPLETED
    assert item.completed_at is not None
    rows = await _rows(db_session)
    assert (rows[anya.id].is_billable, rows[anya.id].price_snapshot) == (True, 1500)
    assert (rows[boris.id].is_billable, rows[boris.id].price_snapshot) == (False, None)
    assert rows[boris.id].attendance == AttendanceStatus.NO_SHOW


async def test_complete_billable_no_show_and_late_cancel(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id, boris.id])
    await service.complete_lesson(
        _actor(owner),
        lesson_id,
        _complete(
            {"student_id": anya.id, "attendance": "no_show", "is_billable": True},
            {"student_id": boris.id, "attendance": "cancelled", "is_billable": True},
        ),
    )
    rows = await _rows(db_session)
    assert rows[anya.id].price_snapshot == 1500
    assert rows[boris.id].price_snapshot == 2000
    assert all(r.is_billable for r in rows.values())


async def test_price_snapshot_not_changed_after_price_update(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id])
    await service.complete_lesson(
        _actor(owner), lesson_id, _complete({"student_id": anya.id, "attendance": "attended"})
    )
    profile = await db_session.get(StudentProfile, anya.id)
    assert profile is not None
    profile.lesson_price = 3000
    await db_session.commit()
    rows = await _rows(db_session)
    assert rows[anya.id].price_snapshot == 1500


async def test_complete_requires_all_participants_exactly(
    service: ScheduleService, owner: User, anya: User, boris: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id, boris.id])
    for marks in (
        [{"student_id": anya.id, "attendance": "attended"}],
        [
            {"student_id": anya.id, "attendance": "attended"},
            {"student_id": boris.id, "attendance": "attended"},
            {"student_id": owner.id, "attendance": "attended"},
        ],
    ):
        with pytest.raises(BusinessRuleError) as raised:
            await service.complete_lesson(_actor(owner), lesson_id, _complete(*marks))
        assert raised.value.code == "marks_mismatch"


async def test_complete_cannot_be_repeated_or_applied_to_cancelled(
    service: ScheduleService, owner: User, manager: User, anya: User
) -> None:
    done = await _lesson(service, owner, [anya.id])
    mark = _complete({"student_id": anya.id, "attendance": "attended"})
    await service.complete_lesson(_actor(owner), done, mark)
    with pytest.raises(BusinessRuleError) as again:
        await service.complete_lesson(_actor(manager), done, mark)
    assert again.value.code == "lesson_already_completed"
    cancelled = await _lesson(service, owner, [anya.id], start=START + timedelta(days=1))
    await service.cancel_lesson(_actor(owner), cancelled, LessonCancel())
    with pytest.raises(BusinessRuleError) as raised:
        await service.complete_lesson(_actor(owner), cancelled, mark)
    assert raised.value.code == "lesson_not_scheduled"


async def test_student_cannot_complete_or_find_missing_lesson(
    service: ScheduleService, owner: User, anya: User
) -> None:
    lesson_id = await _lesson(service, owner, [anya.id])
    mark = _complete({"student_id": anya.id, "attendance": "attended"})
    with pytest.raises(PermissionDeniedError):
        await service.complete_lesson(_actor(anya), lesson_id, mark)
    with pytest.raises(NotFoundError):
        await service.complete_lesson(_actor(owner), 999_999_999, mark)
