"""ExpiryService (T4.10): истечение просроченных выдач на реальной PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import AssignmentStatus, DueMode, HomeworkKind, UserRole
from src.db.models import AuditLog, Homework, HomeworkAssignment, Subject, User
from src.services.expiry import ExpiryService

pytestmark = pytest.mark.security

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.fixture
def service(db_session: AsyncSession) -> ExpiryService:
    return ExpiryService(db_session)


async def _user(db: AsyncSession, role: UserRole, name: str) -> User:
    user = User(role=role, display_name=name)
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def homework(db_session: AsyncSession) -> Homework:
    owner = await _user(db_session, UserRole.OWNER, "Роман")
    subject = Subject(code="informatics_t410", name="Информатика")
    db_session.add(subject)
    await db_session.flush()
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
    name: str,
    *,
    due: datetime,
    extensions: int = 2,
    status: AssignmentStatus = AssignmentStatus.ASSIGNED,
) -> HomeworkAssignment:
    student = await _user(db, UserRole.STUDENT, name)
    row = HomeworkAssignment(
        homework_id=hw.id,
        student_id=student.id,
        status=status,
        original_due_at=due,
        due_at=due,
        extensions_count=extensions,
    )
    db.add(row)
    await db.commit()
    return row


async def state(db: AsyncSession, row: HomeworkAssignment) -> HomeworkAssignment:
    await db.refresh(row)
    return row


async def test_expires_when_deadline_passed_and_extensions_exhausted(
    service: ExpiryService, db_session: AsyncSession, homework: Homework
) -> None:
    row = await assign(db_session, homework, "Аня", due=NOW - timedelta(seconds=1))
    result = await service.expire_due_assignments(NOW)
    assert (result.expired, result.assignment_ids) == (1, [row.id])
    stored = await state(db_session, row)
    assert stored.status == AssignmentStatus.EXPIRED
    assert stored.expired_at == NOW


async def test_deadline_boundary_is_strict(
    service: ExpiryService, db_session: AsyncSession, homework: Homework
) -> None:
    exactly = await assign(db_session, homework, "Борис", due=NOW)
    later = await assign(db_session, homework, "Вера", due=NOW + timedelta(seconds=1))
    just_passed = await assign(db_session, homework, "Глеб", due=NOW - timedelta(microseconds=1))
    result = await service.expire_due_assignments(NOW)
    assert result.assignment_ids == [just_passed.id]
    assert (await state(db_session, exactly)).status == AssignmentStatus.ASSIGNED
    assert (await state(db_session, later)).status == AssignmentStatus.ASSIGNED


@pytest.mark.parametrize("extensions", [0, 1])
async def test_not_expired_while_extensions_remain(
    service: ExpiryService, db_session: AsyncSession, homework: Homework, extensions: int
) -> None:
    row = await assign(
        db_session, homework, "Аня", due=NOW - timedelta(days=10), extensions=extensions
    )
    result = await service.expire_due_assignments(NOW)
    assert result.expired == 0
    stored = await state(db_session, row)
    assert stored.status == AssignmentStatus.ASSIGNED
    assert stored.expired_at is None


async def test_needs_revision_expires_too(
    service: ExpiryService, db_session: AsyncSession, homework: Homework
) -> None:
    row = await assign(
        db_session,
        homework,
        "Аня",
        due=NOW - timedelta(hours=1),
        status=AssignmentStatus.NEEDS_REVISION,
    )
    await service.expire_due_assignments(NOW)
    assert (await state(db_session, row)).status == AssignmentStatus.EXPIRED


@pytest.mark.parametrize(
    "status",
    [AssignmentStatus.SUBMITTED, AssignmentStatus.GRADED, AssignmentStatus.EXPIRED],
)
async def test_other_statuses_are_untouched(
    service: ExpiryService, db_session: AsyncSession, homework: Homework, status: AssignmentStatus
) -> None:
    row = await assign(db_session, homework, "Аня", due=NOW - timedelta(days=3), status=status)
    result = await service.expire_due_assignments(NOW)
    assert result.expired == 0
    assert (await state(db_session, row)).status == status


async def test_second_run_changes_nothing(
    service: ExpiryService, db_session: AsyncSession, homework: Homework
) -> None:
    row = await assign(db_session, homework, "Аня", due=NOW - timedelta(minutes=5))
    first = await service.expire_due_assignments(NOW)
    stored_first = (await state(db_session, row)).expired_at
    later = NOW + timedelta(hours=3)
    second = await service.expire_due_assignments(later)
    assert (first.expired, second.expired) == (1, 0)
    assert (await state(db_session, row)).expired_at == stored_first == NOW
    audits = (
        await db_session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "assignment.expired")
        )
    ).scalar_one()
    assert audits == 1


async def test_several_assignments_are_handled_in_one_run_and_audited_without_actor(
    service: ExpiryService, db_session: AsyncSession, homework: Homework
) -> None:
    rows = [
        await assign(db_session, homework, name, due=NOW - timedelta(hours=index + 1))
        for index, name in enumerate(["Аня", "Борис", "Вера"])
    ]
    result = await service.expire_due_assignments(NOW)
    assert result.assignment_ids == sorted(r.id for r in rows)
    entries = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "assignment.expired")))
        .scalars()
        .all()
    )
    assert len(entries) == 3
    assert {e.actor_user_id for e in entries} == {None}


async def test_uses_current_time_by_default(
    service: ExpiryService, db_session: AsyncSession, homework: Homework
) -> None:
    long_ago = datetime(2020, 1, 1, tzinfo=UTC)
    row = await assign(db_session, homework, "Аня", due=long_ago)
    future = await assign(db_session, homework, "Борис", due=datetime(2099, 1, 1, tzinfo=UTC))
    result = await service.expire_due_assignments()
    assert result.assignment_ids == [row.id]
    assert (await state(db_session, future)).status == AssignmentStatus.ASSIGNED
