"""Ограничения домашних заданий на реальной PostgreSQL (T4.01, docs/04 §5)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkFileRole,
    HomeworkKind,
    UserRole,
)
from src.db.models import (
    ExamType,
    Homework,
    HomeworkAssignment,
    HomeworkFile,
    Subject,
    User,
)

DUE = datetime(2030, 10, 14, 14, 0, tzinfo=UTC)


@pytest.fixture
async def teacher(db_session: AsyncSession) -> User:
    user = User(role=UserRole.OWNER, display_name="Роман")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def student(db_session: AsyncSession) -> User:
    user = User(role=UserRole.STUDENT, display_name="Аня")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def subject(db_session: AsyncSession) -> Subject:
    item = Subject(code="informatics_t401", name="Информатика")
    db_session.add(item)
    await db_session.flush()
    return item


def homework(teacher: User, subject: Subject, **patch: object) -> Homework:
    fields: dict[str, object] = {
        "created_by": teacher.id,
        "subject_id": subject.id,
        "kind": HomeworkKind.REGULAR,
        "title": "Графы",
        "max_score": 13,
        "due_mode": DueMode.FIXED,
    }
    return Homework(**(fields | patch))


async def _assignment(
    db: AsyncSession, hw: Homework, student: User, **patch: object
) -> HomeworkAssignment:
    row = HomeworkAssignment(
        homework_id=hw.id, student_id=student.id, original_due_at=DUE, due_at=DUE, **patch
    )
    db.add(row)
    await db.flush()
    return row


async def test_defaults_of_assignment(
    db_session: AsyncSession, teacher: User, student: User, subject: Subject
) -> None:
    hw = homework(teacher, subject)
    db_session.add(hw)
    await db_session.flush()
    row = await _assignment(db_session, hw, student)
    await db_session.refresh(row)
    assert row.status == AssignmentStatus.ASSIGNED
    assert row.extensions_count == 0
    assert row.graded_after_expiry is False
    assert row.score is None
    assert row.submission_type is None


async def test_max_score_must_be_positive(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    async with db_session.begin_nested():
        db_session.add(homework(teacher, subject, max_score=0))
        with pytest.raises(IntegrityError, match="ck_homeworks_max_score_positive"):
            await db_session.flush()


async def test_mock_exam_requires_exam_type(
    db_session: AsyncSession, teacher: User, subject: Subject
) -> None:
    async with db_session.begin_nested():
        db_session.add(homework(teacher, subject, kind=HomeworkKind.MOCK_EXAM))
        with pytest.raises(IntegrityError, match="ck_homeworks_mock_exam_needs_exam_type"):
            await db_session.flush()
    exam = (await db_session.execute(select(ExamType).limit(1))).scalar_one_or_none()
    if exam is not None:  # справочник заполняется сидами, в тестовой БД его может не быть
        db_session.add(
            homework(teacher, subject, kind=HomeworkKind.MOCK_EXAM, exam_type_id=exam.id)
        )
        await db_session.flush()


async def test_extensions_count_is_limited_to_two(
    db_session: AsyncSession, teacher: User, student: User, subject: Subject
) -> None:
    hw = homework(teacher, subject)
    db_session.add(hw)
    await db_session.flush()
    await _assignment(db_session, hw, student, extensions_count=2)
    other = User(role=UserRole.STUDENT, display_name="Борис")
    db_session.add(other)
    await db_session.flush()
    async with db_session.begin_nested():
        db_session.add(
            HomeworkAssignment(
                homework_id=hw.id,
                student_id=other.id,
                original_due_at=DUE,
                due_at=DUE,
                extensions_count=3,
            )
        )
        with pytest.raises(IntegrityError, match="ck_homework_assignments_extensions_count_range"):
            await db_session.flush()


async def test_one_assignment_per_student_and_homework(
    db_session: AsyncSession, teacher: User, student: User, subject: Subject
) -> None:
    hw = homework(teacher, subject)
    db_session.add(hw)
    await db_session.flush()
    await _assignment(db_session, hw, student)
    async with db_session.begin_nested():
        db_session.add(
            HomeworkAssignment(
                homework_id=hw.id, student_id=student.id, original_due_at=DUE, due_at=DUE
            )
        )
        with pytest.raises(IntegrityError, match="uq_homework_assignments_homework_id_student_id"):
            await db_session.flush()


async def test_negative_score_is_rejected(
    db_session: AsyncSession, teacher: User, student: User, subject: Subject
) -> None:
    hw = homework(teacher, subject)
    db_session.add(hw)
    await db_session.flush()
    async with db_session.begin_nested():
        db_session.add(
            HomeworkAssignment(
                homework_id=hw.id,
                student_id=student.id,
                original_due_at=DUE,
                due_at=DUE,
                score=-1,
            )
        )
        with pytest.raises(IntegrityError, match="ck_homework_assignments_score_nonneg"):
            await db_session.flush()


async def test_deleting_homework_removes_assignments_and_files(
    db_session: AsyncSession, teacher: User, student: User, subject: Subject
) -> None:
    hw = homework(teacher, subject)
    db_session.add(hw)
    await db_session.flush()
    row = await _assignment(db_session, hw, student)
    db_session.add(
        HomeworkFile(
            assignment_id=row.id,
            uploaded_by=student.id,
            role=HomeworkFileRole.STUDENT_SOLUTION,
            s3_key="homework/1/abc.jpg",
            original_name="решение.jpg",
            content_type="image/jpeg",
            size_bytes=1234,
        )
    )
    await db_session.flush()
    await db_session.delete(hw)
    await db_session.flush()
    assert (await db_session.execute(select(HomeworkAssignment))).first() is None
    assert (await db_session.execute(select(HomeworkFile))).first() is None
