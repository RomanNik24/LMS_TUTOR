"""ExtensionService (T4.09, US-05): перенос дедлайна не более двух раз (PostgreSQL)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkKind,
    LessonStatus,
    UserRole,
)
from src.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.db.models import (
    AuditLog,
    Homework,
    HomeworkAssignment,
    HomeworkExtension,
    Lesson,
    LessonParticipant,
    Subject,
    User,
)
from src.schemas.homework import ExtendRequest
from src.services.extensions import ExtensionService

pytestmark = pytest.mark.security

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
DUE = NOW + timedelta(days=2)


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def service(db_session: AsyncSession) -> ExtensionService:
    return ExtensionService(db_session)


async def _user(db: AsyncSession, role: UserRole, name: str) -> User:
    user = User(role=role, display_name=name)
    db.add(user)
    await db.commit()
    return user


def actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман")


@pytest.fixture
async def anya(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Аня")


@pytest.fixture
async def subject(db_session: AsyncSession) -> Subject:
    item = Subject(code="informatics_t409", name="Информатика")
    db_session.add(item)
    await db_session.commit()
    return item


@pytest.fixture
async def homework(db_session: AsyncSession, owner: User, subject: Subject) -> Homework:
    hw = Homework(
        created_by=owner.id,
        subject_id=subject.id,
        kind=HomeworkKind.REGULAR,
        title="Графы",
        max_score=13,
        due_mode=DueMode.FIXED,
    )
    db_session.add(hw)
    await db_session.commit()
    return hw


async def assign(
    db: AsyncSession,
    hw: Homework,
    student: User,
    status: AssignmentStatus = AssignmentStatus.ASSIGNED,
    **patch: object,
) -> HomeworkAssignment:
    fields: dict[str, object] = {"original_due_at": DUE, "due_at": DUE}
    row = HomeworkAssignment(
        homework_id=hw.id, student_id=student.id, status=status, **(fields | patch)
    )
    db.add(row)
    await db.commit()
    return row


async def lesson_for(
    db: AsyncSession,
    teacher: User,
    subject: Subject,
    student: User,
    start: datetime,
    status: LessonStatus = LessonStatus.SCHEDULED,
) -> None:
    lesson = Lesson(
        teacher_id=teacher.id,
        subject_id=subject.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
        status=status,
    )
    db.add(lesson)
    await db.flush()
    db.add(LessonParticipant(lesson_id=lesson.id, student_id=student.id))
    await db.commit()


async def journal(db: AsyncSession, assignment_id: int) -> list[HomeworkExtension]:
    stmt = (
        select(HomeworkExtension)
        .where(HomeworkExtension.assignment_id == assignment_id)
        .order_by(HomeworkExtension.id)
    )
    return list((await db.execute(stmt)).scalars())


# ---------------------------------------------------------------- на следующее занятие


async def test_extends_to_nearest_lesson_after_current_due(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    subject: Subject,
) -> None:
    before = DUE - timedelta(hours=5)  # урок до срока не подходит
    first = DUE + timedelta(days=1)
    second = DUE + timedelta(days=4)
    await lesson_for(db_session, owner, subject, anya, second)
    await lesson_for(db_session, owner, subject, anya, first)
    await lesson_for(db_session, owner, subject, anya, before)
    await lesson_for(
        db_session, owner, subject, anya, DUE + timedelta(hours=3), LessonStatus.CANCELLED
    )
    row = await assign(db_session, homework, anya)
    result = await service.extend_deadline(actor(owner), row.id, ExtendRequest())
    assert (result.old_due_at, result.new_due_at) == (DUE, first)
    assert (result.extensions_count, result.extensions_left) == (1, 1)
    await db_session.refresh(row)
    assert row.due_at == first
    assert row.original_due_at == DUE  # первоначальный срок не меняется
    (entry,) = await journal(db_session, row.id)
    assert (entry.old_due_at, entry.new_due_at, entry.created_by) == (DUE, first, owner.id)


async def test_second_extension_goes_to_the_next_lesson_again(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    subject: Subject,
) -> None:
    first = DUE + timedelta(days=1)
    second = DUE + timedelta(days=4)
    await lesson_for(db_session, owner, subject, anya, first)
    await lesson_for(db_session, owner, subject, anya, second)
    row = await assign(db_session, homework, anya)
    await service.extend_deadline(actor(owner), row.id, ExtendRequest())
    result = await service.extend_deadline(actor(owner), row.id, ExtendRequest())
    assert result.new_due_at == second
    assert (result.extensions_count, result.extensions_left) == (2, 0)
    assert len(await journal(db_session, row.id)) == 2


async def test_third_extension_is_refused(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    for days in (3, 6):
        await service.extend_deadline(
            actor(owner), row.id, ExtendRequest(due_at=DUE + timedelta(days=days))
        )
    with pytest.raises(BusinessRuleError) as raised:
        await service.extend_deadline(
            actor(owner), row.id, ExtendRequest(due_at=DUE + timedelta(days=9))
        )
    assert raised.value.code == "homework_extension_limit"
    assert raised.value.http_status == 400
    await db_session.refresh(row)
    assert (row.extensions_count, row.due_at) == (2, DUE + timedelta(days=6))
    assert len(await journal(db_session, row.id)) == 2


async def test_without_next_lesson_a_manual_date_is_needed(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(BusinessRuleError) as raised:
        await service.extend_deadline(actor(owner), row.id, ExtendRequest())
    assert raised.value.code == "no_next_lesson"
    await db_session.refresh(row)
    assert row.extensions_count == 0
    assert await journal(db_session, row.id) == []
    manual = DUE + timedelta(days=5)
    result = await service.extend_deadline(actor(owner), row.id, ExtendRequest(due_at=manual))
    assert result.new_due_at == manual
    assert result.extensions_count == 1  # ручной перенос тоже считается
    (entry,) = await audit(db_session)
    assert entry.data["manual"] is True


async def audit(db: AsyncSession) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == "assignment.extended").order_by(AuditLog.id)
    return list((await db.execute(stmt)).scalars())


async def test_overdue_assignment_moves_to_a_lesson_after_now_not_before(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    subject: Subject,
) -> None:
    old_due = NOW - timedelta(days=3)
    unmarked = NOW - timedelta(days=1)  # урок прошёл, но не отмечен: в прошлое не переносим
    future = NOW + timedelta(days=2)
    await lesson_for(db_session, owner, subject, anya, unmarked)
    await lesson_for(db_session, owner, subject, anya, future)
    row = await assign(db_session, homework, anya, original_due_at=old_due, due_at=old_due)
    result = await service.extend_deadline(actor(owner), row.id, ExtendRequest())
    assert result.new_due_at == future


# ---------------------------------------------------------------- дата вручную


async def test_manual_date_must_be_in_the_future_and_later_than_current(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(ValidationError) as past:
        await service.extend_deadline(
            actor(owner), row.id, ExtendRequest(due_at=NOW - timedelta(hours=1))
        )
    assert past.value.code == "due_in_past"
    with pytest.raises(ValidationError) as same:
        await service.extend_deadline(actor(owner), row.id, ExtendRequest(due_at=DUE))
    assert same.value.code == "due_not_later"
    with pytest.raises(ValidationError):
        await service.extend_deadline(
            actor(owner), row.id, ExtendRequest(due_at=DUE - timedelta(hours=1))
        )
    await db_session.refresh(row)
    assert (row.extensions_count, row.due_at) == (0, DUE)


# ---------------------------------------------------------------- статусы и права


async def test_needs_revision_can_be_extended(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya, AssignmentStatus.NEEDS_REVISION)
    result = await service.extend_deadline(
        actor(owner), row.id, ExtendRequest(due_at=DUE + timedelta(days=2))
    )
    assert result.extensions_count == 1


@pytest.mark.parametrize(
    "status", [AssignmentStatus.SUBMITTED, AssignmentStatus.GRADED, AssignmentStatus.EXPIRED]
)
async def test_other_statuses_cannot_be_extended(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    status: AssignmentStatus,
) -> None:
    row = await assign(db_session, homework, anya, status)
    with pytest.raises(BusinessRuleError) as raised:
        await service.extend_deadline(
            actor(owner), row.id, ExtendRequest(due_at=DUE + timedelta(days=2))
        )
    assert raised.value.code == "assignment_not_extendable"
    assert await journal(db_session, row.id) == []


async def test_students_cannot_extend_and_missing_is_404(
    service: ExtensionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(PermissionDeniedError):
        await service.extend_deadline(
            actor(anya), row.id, ExtendRequest(due_at=DUE + timedelta(days=2))
        )
    with pytest.raises(NotFoundError) as missing:
        await service.extend_deadline(actor(owner), 999_999_999, ExtendRequest())
    assert missing.value.code == "assignment_not_found"
    await db_session.refresh(row)
    assert row.extensions_count == 0
