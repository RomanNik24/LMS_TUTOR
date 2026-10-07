"""GradingService (T4.08, US-06): оценка, возврат на доработку, просроченные (PostgreSQL)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import AssignmentStatus, DueMode, HomeworkKind, UserRole
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
    Lesson,
    LessonParticipant,
    Subject,
    User,
)
from src.schemas.homework import GradeRequest, ReturnRequest
from src.services.grading import GradingService

pytestmark = pytest.mark.security

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
DUE = NOW + timedelta(days=2)


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def service(db_session: AsyncSession) -> GradingService:
    return GradingService(db_session)


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
async def manager(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.MANAGER, "Мария")


@pytest.fixture
async def anya(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Аня")


@pytest.fixture
async def subject(db_session: AsyncSession) -> Subject:
    item = Subject(code="informatics_t408", name="Информатика")
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
    status: AssignmentStatus = AssignmentStatus.SUBMITTED,
    **patch: object,
) -> HomeworkAssignment:
    row = HomeworkAssignment(
        homework_id=hw.id,
        student_id=student.id,
        status=status,
        original_due_at=DUE,
        due_at=DUE,
        **patch,
    )
    db.add(row)
    await db.commit()
    return row


async def audit(db: AsyncSession, action: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
    return list((await db.execute(stmt)).scalars())


# ---------------------------------------------------------------- оценка


async def test_grade_submitted_assignment(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    manager: User,
) -> None:
    row = await assign(db_session, homework, anya)
    result = await service.grade_assignment(
        actor(manager), row.id, GradeRequest(score=11, comment="Хорошо")
    )
    assert result.status == AssignmentStatus.GRADED
    assert (result.score, result.max_score, result.score_percent) == (11, 13, 85)
    assert result.graded_at == NOW
    assert result.graded_after_expiry is False
    await db_session.refresh(row)
    assert (row.score, row.graded_by, row.teacher_comment) == (11, manager.id, "Хорошо")
    (entry,) = await audit(db_session, "assignment.graded")
    assert entry.data == {"score": 11, "max_score": 13}
    assert entry.actor_user_id == manager.id


@pytest.mark.parametrize("score", [0, 13])
async def test_score_edges_are_allowed(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    score: int,
) -> None:
    row = await assign(db_session, homework, anya)
    result = await service.grade_assignment(actor(owner), row.id, GradeRequest(score=score))
    assert result.score == score


@pytest.mark.parametrize("score", [-1, 14, 1000])
async def test_score_out_of_range(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    score: int,
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(BusinessRuleError) as raised:
        await service.grade_assignment(actor(owner), row.id, GradeRequest(score=score))
    assert raised.value.code == "score_out_of_range"
    assert raised.value.http_status == 400
    assert raised.value.details == {"max_score": 13}
    await db_session.refresh(row)
    assert row.status == AssignmentStatus.SUBMITTED
    assert row.score is None


@pytest.mark.parametrize("status", [AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION])
async def test_not_submitted_assignment_cannot_be_graded(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    status: AssignmentStatus,
) -> None:
    row = await assign(db_session, homework, anya, status)
    with pytest.raises(BusinessRuleError) as raised:
        await service.grade_assignment(actor(owner), row.id, GradeRequest(score=5))
    assert raised.value.code == "assignment_not_gradable"


async def test_expired_assignment_can_be_graded_manually_with_flag_and_audit(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(
        db_session,
        homework,
        anya,
        AssignmentStatus.EXPIRED,
        extensions_count=2,
        expired_at=NOW - timedelta(days=1),
    )
    result = await service.grade_assignment(actor(owner), row.id, GradeRequest(score=7))
    assert result.status == AssignmentStatus.GRADED
    assert result.graded_after_expiry is True
    await db_session.refresh(row)
    assert row.graded_after_expiry is True
    assert row.expired_at is not None  # история истечения остаётся
    assert await audit(db_session, "assignment.graded") == []
    (entry,) = await audit(db_session, "assignment.graded_after_expiry")
    assert entry.entity_id == row.id
    assert entry.data == {"score": 7, "max_score": 13}


async def test_regrade_updates_score_and_records_previous_one(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    await service.grade_assignment(actor(owner), row.id, GradeRequest(score=8))
    result = await service.grade_assignment(actor(owner), row.id, GradeRequest(score=10))
    assert result.score == 10
    entries = await audit(db_session, "assignment.graded")
    assert entries[-1].data == {"score": 10, "max_score": 13, "previous_score": 8}


async def test_regrade_keeps_the_after_expiry_flag(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya, AssignmentStatus.EXPIRED, extensions_count=2)
    await service.grade_assignment(actor(owner), row.id, GradeRequest(score=3))
    result = await service.grade_assignment(actor(owner), row.id, GradeRequest(score=4))
    assert result.graded_after_expiry is True


async def test_students_cannot_grade_or_return_and_missing_is_404(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(PermissionDeniedError):
        await service.grade_assignment(actor(anya), row.id, GradeRequest(score=13))
    with pytest.raises(PermissionDeniedError):
        await service.return_for_revision(actor(anya), row.id, ReturnRequest(comment="x"))
    with pytest.raises(NotFoundError) as missing:
        await service.grade_assignment(actor(owner), 999_999_999, GradeRequest(score=1))
    assert missing.value.code == "assignment_not_found"
    await db_session.refresh(row)
    assert row.status == AssignmentStatus.SUBMITTED


# ---------------------------------------------------------------- возврат на доработку


async def lesson_for(
    db: AsyncSession, teacher: User, subject: Subject, student: User, start: datetime
) -> None:
    lesson = Lesson(
        teacher_id=teacher.id,
        subject_id=subject.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
    )
    db.add(lesson)
    await db.flush()
    db.add(LessonParticipant(lesson_id=lesson.id, student_id=student.id))
    await db.commit()


async def test_return_defaults_to_next_lesson(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    subject: Subject,
) -> None:
    next_lesson = NOW + timedelta(days=4)
    await lesson_for(db_session, owner, subject, anya, next_lesson + timedelta(days=3))
    await lesson_for(db_session, owner, subject, anya, next_lesson)
    row = await assign(db_session, homework, anya)
    result = await service.return_for_revision(
        actor(owner), row.id, ReturnRequest(comment="  Исправьте задачу 3  ")
    )
    assert result.status == AssignmentStatus.NEEDS_REVISION
    assert result.due_at == next_lesson
    assert result.teacher_comment == "Исправьте задачу 3"
    await db_session.refresh(row)
    assert row.due_at == next_lesson
    assert row.original_due_at == DUE  # первоначальный срок не меняется
    assert row.extensions_count == 0  # возврат не считается переносом
    (entry,) = await audit(db_session, "assignment.returned")
    assert entry.data["new_due_at"] == next_lesson.isoformat()


async def test_return_with_explicit_due(
    service: GradingService, db_session: AsyncSession, homework: Homework, anya: User, owner: User
) -> None:
    row = await assign(db_session, homework, anya)
    new_due = NOW + timedelta(days=9)
    result = await service.return_for_revision(
        actor(owner), row.id, ReturnRequest(comment="Доделать", new_due_at=new_due)
    )
    assert result.due_at == new_due


async def test_return_without_next_lesson_needs_explicit_due(
    service: GradingService, db_session: AsyncSession, homework: Homework, anya: User, owner: User
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(BusinessRuleError) as raised:
        await service.return_for_revision(actor(owner), row.id, ReturnRequest(comment="Доделать"))
    assert raised.value.code == "no_next_lesson"
    await db_session.refresh(row)
    assert row.status == AssignmentStatus.SUBMITTED


async def test_return_due_in_the_past_is_rejected(
    service: GradingService, db_session: AsyncSession, homework: Homework, anya: User, owner: User
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(ValidationError) as raised:
        await service.return_for_revision(
            actor(owner), row.id, ReturnRequest(comment="x", new_due_at=NOW - timedelta(hours=1))
        )
    assert raised.value.code == "due_in_past"


@pytest.mark.parametrize(
    "status",
    [
        AssignmentStatus.ASSIGNED,
        AssignmentStatus.NEEDS_REVISION,
        AssignmentStatus.GRADED,
        AssignmentStatus.EXPIRED,
    ],
)
async def test_only_submitted_can_be_returned(
    service: GradingService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
    status: AssignmentStatus,
) -> None:
    row = await assign(db_session, homework, anya, status)
    with pytest.raises(BusinessRuleError) as raised:
        await service.return_for_revision(
            actor(owner), row.id, ReturnRequest(comment="x", new_due_at=NOW + timedelta(days=1))
        )
    assert raised.value.code == "assignment_not_returnable"
