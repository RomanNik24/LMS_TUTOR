"""SubmissionService (T4.07, US-04): сдача файлами и «Сделал» на реальной PostgreSQL."""

import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkKind,
    SubmissionType,
    UserRole,
)
from src.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
)
from src.db.models import Homework, HomeworkAssignment, Subject, User
from src.schemas.homework import SubmitRequest
from src.services.files import FileService
from src.services.submissions import SubmissionService

pytestmark = pytest.mark.security

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
DUE = NOW + timedelta(days=2)
PDF = b"%PDF-1.4\n" + b"x" * 200


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        del content_type
        self.objects[key] = data

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def presign_get(self, key: str, *, expires: int = 600) -> str:
        return f"https://files.example/{key}?exp={expires}"


async def _user(db: AsyncSession, role: UserRole, name: str) -> User:
    user = User(role=role, display_name=name)
    db.add(user)
    await db.commit()
    return user


def actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


@pytest.fixture
def submissions(db_session: AsyncSession) -> SubmissionService:
    return SubmissionService(db_session)


@pytest.fixture
def files(db_session: AsyncSession) -> FileService:
    return FileService(db_session, FakeStorage())


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман")


@pytest.fixture
async def anya(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Аня")


@pytest.fixture
async def boris(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Борис")


@pytest.fixture
async def homework(db_session: AsyncSession, owner: User) -> Homework:
    subject = Subject(code="informatics_t407", name="Информатика")
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
    student: User,
    *,
    status: AssignmentStatus = AssignmentStatus.ASSIGNED,
    original_due: datetime = DUE,
    due: datetime = DUE,
    extensions: int = 0,
) -> HomeworkAssignment:
    row = HomeworkAssignment(
        homework_id=hw.id,
        student_id=student.id,
        status=status,
        original_due_at=original_due,
        due_at=due,
        extensions_count=extensions,
    )
    db.add(row)
    await db.commit()
    return row


def photo() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "green").save(buffer, format="JPEG")
    return buffer.getvalue()


async def reload(db: AsyncSession, row: HomeworkAssignment) -> HomeworkAssignment:
    await db.refresh(row)
    return row


# ---------------------------------------------------------------- сдача файлами


async def test_submit_requires_at_least_one_file(
    submissions: SubmissionService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(BusinessRuleError) as raised:
        await submissions.submit_files(actor(anya), row.id, SubmitRequest())
    assert raised.value.code == "no_files"
    assert (await reload(db_session, row)).status == AssignmentStatus.ASSIGNED


async def test_submit_with_files_moves_to_submitted_and_marks_on_time(
    submissions: SubmissionService,
    files: FileService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    await files.upload_solution(actor(anya), row.id, "1.jpg", photo())
    await files.upload_solution(actor(anya), row.id, "2.pdf", PDF)
    result = await submissions.submit_files(
        actor(anya), row.id, SubmitRequest(student_comment="  Сделал всё  ")
    )
    assert result.status == AssignmentStatus.SUBMITTED
    assert result.submission_type == SubmissionType.FILES
    assert result.files_count == 2
    assert result.submitted_at == NOW
    assert result.on_time is True
    stored = await reload(db_session, row)
    assert stored.status == AssignmentStatus.SUBMITTED
    assert stored.submitted_at == NOW
    assert stored.student_comment == "Сделал всё"


async def test_files_are_locked_after_submission(
    submissions: SubmissionService,
    files: FileService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    await files.upload_solution(actor(anya), row.id, "1.pdf", PDF)
    await submissions.submit_files(actor(anya), row.id, SubmitRequest())
    with pytest.raises(BusinessRuleError) as raised:
        await files.upload_solution(actor(anya), row.id, "2.pdf", PDF)
    assert raised.value.code == "assignment_not_editable"


async def test_second_submission_is_rejected(
    submissions: SubmissionService,
    files: FileService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    await files.upload_solution(actor(anya), row.id, "1.pdf", PDF)
    await submissions.submit_files(actor(anya), row.id, SubmitRequest())
    with pytest.raises(BusinessRuleError) as raised:
        await submissions.submit_files(actor(anya), row.id, SubmitRequest())
    assert raised.value.code == "assignment_not_submittable"


# ---------------------------------------------------------------- сроки


async def test_overdue_assignment_can_still_be_submitted_but_is_not_on_time(
    submissions: SubmissionService,
    files: FileService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    """Срок вышел, но переносы не исчерпаны: ученик сдаёт, преподаватель решает."""
    past = NOW - timedelta(days=1)
    row = await assign(db_session, homework, anya, original_due=past, due=past, extensions=1)
    await files.upload_solution(actor(anya), row.id, "1.pdf", PDF)
    result = await submissions.submit_files(actor(anya), row.id, SubmitRequest())
    assert result.status == AssignmentStatus.SUBMITTED
    assert result.on_time is False


async def test_on_time_is_measured_against_original_due_not_extended_one(
    submissions: SubmissionService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(
        db_session,
        homework,
        anya,
        original_due=NOW - timedelta(hours=1),
        due=NOW + timedelta(days=3),
        extensions=1,
    )
    result = await submissions.submit_self_reported(actor(anya), row.id, SubmitRequest())
    assert result.on_time is False


async def test_submission_exactly_at_original_deadline_is_on_time(
    submissions: SubmissionService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(db_session, homework, anya, original_due=NOW, due=NOW)
    assert (await submissions.submit_self_reported(actor(anya), row.id, SubmitRequest())).on_time


async def test_expired_assignment_cannot_be_submitted(
    submissions: SubmissionService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    past = NOW - timedelta(days=5)
    row = await assign(
        db_session,
        homework,
        anya,
        status=AssignmentStatus.EXPIRED,
        original_due=past,
        due=past,
        extensions=2,
    )
    for submit in (submissions.submit_files, submissions.submit_self_reported):
        with pytest.raises(BusinessRuleError) as raised:
            await submit(actor(anya), row.id, SubmitRequest())
        assert raised.value.code == "assignment_expired"
    assert (await reload(db_session, row)).status == AssignmentStatus.EXPIRED


@pytest.mark.parametrize("status", [AssignmentStatus.SUBMITTED, AssignmentStatus.GRADED])
async def test_submitted_or_graded_cannot_be_submitted_again(
    submissions: SubmissionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    status: AssignmentStatus,
) -> None:
    row = await assign(db_session, homework, anya, status=status)
    with pytest.raises(BusinessRuleError) as raised:
        await submissions.submit_self_reported(actor(anya), row.id, SubmitRequest())
    assert raised.value.code == "assignment_not_submittable"


async def test_needs_revision_can_be_resubmitted_and_keeps_teacher_comment(
    submissions: SubmissionService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(db_session, homework, anya, status=AssignmentStatus.NEEDS_REVISION)
    row.teacher_comment = "Исправьте задачу 3"
    await db_session.commit()
    result = await submissions.submit_self_reported(actor(anya), row.id, SubmitRequest())
    assert result.status == AssignmentStatus.SUBMITTED
    assert (await reload(db_session, row)).teacher_comment == "Исправьте задачу 3"


# ---------------------------------------------------------------- «Сделал»


async def test_self_reported_needs_no_files(
    submissions: SubmissionService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(db_session, homework, anya)
    result = await submissions.submit_self_reported(
        actor(anya), row.id, SubmitRequest(student_comment="Решил в тетради")
    )
    assert result.submission_type == SubmissionType.SELF_REPORTED
    assert result.files_count == 0
    stored = await reload(db_session, row)
    assert stored.submission_type == SubmissionType.SELF_REPORTED
    assert stored.student_comment == "Решил в тетради"


async def test_self_reported_with_uploaded_files_is_recorded_as_files(
    submissions: SubmissionService,
    files: FileService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    await files.upload_solution(actor(anya), row.id, "1.pdf", PDF)
    result = await submissions.submit_self_reported(actor(anya), row.id, SubmitRequest())
    assert result.submission_type == SubmissionType.FILES
    assert result.files_count == 1


# ---------------------------------------------------------------- права


async def test_foreign_and_missing_assignment_look_the_same(
    submissions: SubmissionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    boris: User,
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(NotFoundError) as foreign:
        await submissions.submit_self_reported(actor(boris), row.id, SubmitRequest())
    with pytest.raises(NotFoundError) as missing:
        await submissions.submit_self_reported(actor(boris), 999_999_999, SubmitRequest())
    assert foreign.value.code == missing.value.code == "assignment_not_found"
    assert (await reload(db_session, row)).status == AssignmentStatus.ASSIGNED


async def test_staff_cannot_submit_for_students(
    submissions: SubmissionService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    for submit in (submissions.submit_files, submissions.submit_self_reported):
        with pytest.raises(PermissionDeniedError):
            await submit(actor(owner), row.id, SubmitRequest())
