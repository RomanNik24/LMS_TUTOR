"""HomeworkService (T4.06, US-03): создание и выдача заданий на реальной PostgreSQL."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import (
    AssignmentStatus,
    ExamKind,
    ExamResultKind,
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
    ExamType,
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    Subject,
    User,
)
from src.schemas.homework import AssigneesAdd, HomeworkCreate
from src.services.homework import HomeworkService

pytestmark = pytest.mark.security

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
FUTURE = NOW + timedelta(days=5)


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def service(db_session: AsyncSession) -> HomeworkService:
    return HomeworkService(db_session)


async def _user(db: AsyncSession, role: UserRole, name: str, *, active: bool = True) -> User:
    user = User(role=role, display_name=name, is_active=active)
    db.add(user)
    await db.commit()
    return user


def actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман")


@pytest.fixture
async def students(db_session: AsyncSession) -> list[User]:
    return [await _user(db_session, UserRole.STUDENT, name) for name in ("Аня", "Борис", "Вера")]


@pytest.fixture
async def informatics(db_session: AsyncSession) -> Subject:
    subject = Subject(code="informatics", name="Информатика")
    db_session.add(subject)
    await db_session.commit()
    return subject


@pytest.fixture
async def exam_type(db_session: AsyncSession, informatics: Subject) -> ExamType:
    exam = ExamType(
        code="ege_informatics",
        subject_id=informatics.id,
        kind=ExamKind.EGE,
        result_kind=ExamResultKind.TEST_100,
        max_primary=29,
        name="ЕГЭ информатика",
        config={},
    )
    db_session.add(exam)
    await db_session.commit()
    return exam


def regular(student_ids: list[int], **patch: object) -> HomeworkCreate:
    base: dict[str, object] = {
        "kind": "regular",
        "title": "Графы",
        "subject_code": "informatics",
        "max_score": 13,
        "due_mode": "fixed",
        "due_at": FUTURE,
        "student_ids": student_ids,
    }
    return HomeworkCreate.model_validate(base | patch)


async def lesson_for(
    db: AsyncSession,
    teacher: User,
    subject: Subject,
    student: User,
    start: datetime,
    status: LessonStatus = LessonStatus.SCHEDULED,
) -> Lesson:
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
    return lesson


async def count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# ---------------------------------------------------------------- US-03: выдача группе


async def test_group_of_three_gets_one_homework_and_three_assignments(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    item = await service.create_homework(actor(owner), regular([s.id for s in students]))
    assert await count(db_session, Homework) == 1
    assert await count(db_session, HomeworkAssignment) == 3
    assert [a.student_id for a in item.assignments] == [s.id for s in students]
    assert {a.status for a in item.assignments} == {AssignmentStatus.ASSIGNED}
    assert {a.extensions_count for a in item.assignments} == {0}
    assert all(a.due_at == a.original_due_at == FUTURE for a in item.assignments)
    assert (item.subject_code, item.max_score, item.title) == ("informatics", 13, "Графы")
    audit = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "homework.created"))
    ).scalar_one()
    assert audit.data == {"kind": "regular", "assignees": 3}


async def test_assignments_are_independent_per_student(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    item = await service.create_homework(actor(owner), regular([s.id for s in students]))
    first = await db_session.get(HomeworkAssignment, item.assignments[0].id)
    assert first is not None
    first.status = AssignmentStatus.GRADED
    first.score = 11
    await db_session.commit()
    fresh = await service.get_homework(actor(owner), item.id)
    assert [a.status for a in fresh.assignments] == [
        AssignmentStatus.GRADED,
        AssignmentStatus.ASSIGNED,
        AssignmentStatus.ASSIGNED,
    ]


# ---------------------------------------------------------------- сроки


async def test_fixed_due_in_the_past_is_rejected(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    with pytest.raises(ValidationError) as raised:
        await service.create_homework(
            actor(owner), regular([students[0].id], due_at=NOW - timedelta(minutes=1))
        )
    assert raised.value.code == "due_in_past"
    assert await count(db_session, Homework) == 0


async def test_next_lesson_due_is_start_of_each_students_next_lesson(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    anya, boris, _ = students
    soon = NOW + timedelta(days=1)
    later = NOW + timedelta(days=3)
    boris_lesson = NOW + timedelta(days=4)  # у одного преподавателя уроки не пересекаются
    await lesson_for(db_session, owner, informatics, anya, later)
    await lesson_for(db_session, owner, informatics, anya, soon)  # ближайший у Ани
    await lesson_for(db_session, owner, informatics, boris, boris_lesson)
    # не считаются: прошедший, отменённый, проведённый
    await lesson_for(db_session, owner, informatics, boris, NOW - timedelta(days=1))
    await lesson_for(
        db_session, owner, informatics, boris, NOW + timedelta(hours=2), LessonStatus.CANCELLED
    )
    item = await service.create_homework(
        actor(owner),
        regular([anya.id, boris.id], due_mode="next_lesson", due_at=None),
    )
    due = {a.student_id: a.due_at for a in item.assignments}
    assert due == {anya.id: soon, boris.id: boris_lesson}


async def test_next_lesson_without_lesson_is_an_error_naming_the_students(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    anya, boris, _ = students
    await lesson_for(db_session, owner, informatics, anya, NOW + timedelta(days=1))
    with pytest.raises(BusinessRuleError) as raised:
        await service.create_homework(
            actor(owner), regular([anya.id, boris.id], due_mode="next_lesson", due_at=None)
        )
    assert raised.value.code == "no_next_lesson"
    assert raised.value.details == {"student_ids": [boris.id]}
    assert await count(db_session, Homework) == 0


async def test_next_lesson_uses_fallback_due_for_students_without_lesson(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    anya, boris, _ = students
    soon = NOW + timedelta(days=1)
    await lesson_for(db_session, owner, informatics, anya, soon)
    item = await service.create_homework(
        actor(owner),
        regular([anya.id, boris.id], due_mode="next_lesson", due_at=FUTURE),
    )
    assert {a.student_id: a.due_at for a in item.assignments} == {anya.id: soon, boris.id: FUTURE}


# ---------------------------------------------------------------- пробники


async def test_mock_exam_takes_subject_and_default_score_from_exam_type(
    service: HomeworkService,
    owner: User,
    students: list[User],
    exam_type: ExamType,
) -> None:
    item = await service.create_homework(
        actor(owner),
        HomeworkCreate.model_validate(
            {
                "kind": "mock_exam",
                "title": "Пробник №1",
                "exam_type_id": exam_type.id,
                "due_mode": "fixed",
                "due_at": FUTURE,
                "student_ids": [students[0].id],
            }
        ),
    )
    assert (item.subject_code, item.max_score, item.exam_type_id) == (
        "informatics",
        29,
        exam_type.id,
    )


async def test_mock_exam_max_score_can_be_overridden(
    service: HomeworkService, owner: User, students: list[User], exam_type: ExamType
) -> None:
    item = await service.create_homework(
        actor(owner),
        HomeworkCreate.model_validate(
            {
                "kind": "mock_exam",
                "title": "Пробник на 27",
                "exam_type_id": exam_type.id,
                "max_score": 27,
                "due_mode": "fixed",
                "due_at": FUTURE,
                "student_ids": [students[0].id],
            }
        ),
    )
    assert item.max_score == 27


async def test_mock_exam_with_unknown_exam_type_or_other_subject(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    exam_type: ExamType,
) -> None:
    db_session.add(Subject(code="math", name="Математика"))
    await db_session.commit()

    def exam(**patch: object) -> HomeworkCreate:
        base: dict[str, object] = {
            "kind": "mock_exam",
            "title": "Пробник",
            "exam_type_id": exam_type.id,
            "due_mode": "fixed",
            "due_at": FUTURE,
            "student_ids": [students[0].id],
        }
        return HomeworkCreate.model_validate(base | patch)

    with pytest.raises(ValidationError) as unknown:
        await service.create_homework(actor(owner), exam(exam_type_id=999_999))
    assert unknown.value.code == "unknown_exam_type"
    with pytest.raises(ValidationError) as mismatch:
        await service.create_homework(actor(owner), exam(subject_code="math"))
    assert mismatch.value.code == "subject_mismatch"


# ---------------------------------------------------------------- ошибки и права


async def test_unknown_subject_unknown_lesson_and_bad_students(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    with pytest.raises(ValidationError) as subject:
        await service.create_homework(
            actor(owner), regular([students[0].id], subject_code="physics")
        )
    assert subject.value.code == "unknown_subject"
    with pytest.raises(ValidationError) as lesson:
        await service.create_homework(actor(owner), regular([students[0].id], lesson_id=999_999))
    assert lesson.value.code == "unknown_lesson"
    archived = await _user(db_session, UserRole.STUDENT, "Бывший", active=False)
    with pytest.raises(BusinessRuleError) as gone:
        await service.create_homework(actor(owner), regular([archived.id]))
    assert gone.value.code == "student_archived"
    with pytest.raises(NotFoundError):
        await service.create_homework(actor(owner), regular([999_999_999]))
    with pytest.raises(NotFoundError):
        await service.create_homework(actor(owner), regular([owner.id]))
    assert await count(db_session, Homework) == 0


async def test_linked_lesson_is_saved(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    lesson = await lesson_for(db_session, owner, informatics, students[0], FUTURE)
    item = await service.create_homework(
        actor(owner), regular([students[0].id], lesson_id=lesson.id)
    )
    assert item.lesson_id == lesson.id


async def test_student_cannot_create_assign_or_read(
    service: HomeworkService,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    item = await service.create_homework(actor(owner), regular([students[0].id]))
    student = actor(students[0])
    with pytest.raises(PermissionDeniedError):
        await service.create_homework(student, regular([students[0].id]))
    with pytest.raises(PermissionDeniedError):
        await service.add_assignees(student, item.id, AssigneesAdd(student_ids=[students[1].id]))
    with pytest.raises(PermissionDeniedError):
        await service.get_homework(student, item.id)
    with pytest.raises(PermissionDeniedError):
        await service.list_homeworks(student)


# ---------------------------------------------------------------- add_assignees


async def test_add_assignees_skips_existing_and_inherits_fixed_due(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    anya, boris, vera = students
    item = await service.create_homework(actor(owner), regular([anya.id]))
    updated = await service.add_assignees(
        actor(owner), item.id, AssigneesAdd(student_ids=[anya.id, boris.id, vera.id])
    )
    assert [a.student_id for a in updated.assignments] == [anya.id, boris.id, vera.id]
    assert {a.due_at for a in updated.assignments} == {FUTURE}
    assert await count(db_session, HomeworkAssignment) == 3
    # повторное добавление ничего не меняет
    again = await service.add_assignees(
        actor(owner), item.id, AssigneesAdd(student_ids=[anya.id, boris.id])
    )
    assert len(again.assignments) == 3


async def test_add_assignees_uses_next_lesson_and_checks_homework(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    anya, boris, _ = students
    first_start = NOW + timedelta(days=1)
    await lesson_for(db_session, owner, informatics, anya, first_start)
    item = await service.create_homework(
        actor(owner), regular([anya.id], due_mode="next_lesson", due_at=None)
    )
    boris_start = NOW + timedelta(days=2)
    await lesson_for(db_session, owner, informatics, boris, boris_start)
    updated = await service.add_assignees(
        actor(owner), item.id, AssigneesAdd(student_ids=[boris.id])
    )
    assert {a.student_id: a.due_at for a in updated.assignments} == {
        anya.id: first_start,
        boris.id: boris_start,
    }
    with pytest.raises(NotFoundError) as missing:
        await service.add_assignees(actor(owner), 999_999, AssigneesAdd(student_ids=[boris.id]))
    assert missing.value.code == "homework_not_found"


# ---------------------------------------------------------------- список


async def test_list_shows_submitted_of_assigned_counts_and_pages(
    service: HomeworkService,
    db_session: AsyncSession,
    owner: User,
    students: list[User],
    informatics: Subject,
) -> None:
    first = await service.create_homework(actor(owner), regular([s.id for s in students]))
    second = await service.create_homework(actor(owner), regular([students[0].id], title="Циклы"))
    rows = (await db_session.execute(select(HomeworkAssignment))).scalars().all()
    ours = [r for r in rows if r.homework_id == first.id]
    ours[0].status = AssignmentStatus.SUBMITTED
    ours[1].status = AssignmentStatus.GRADED
    await db_session.commit()
    page = await service.list_homeworks(actor(owner))
    assert page.total == 2
    assert [i.id for i in page.items] == [second.id, first.id]  # новые сверху
    by_id = {i.id: i for i in page.items}
    assert (by_id[first.id].assigned_count, by_id[first.id].submitted_count) == (3, 2)
    assert (by_id[second.id].assigned_count, by_id[second.id].submitted_count) == (1, 0)
    one = await service.list_homeworks(actor(owner), limit=1, offset=1)
    assert [i.id for i in one.items] == [first.id]
    with pytest.raises(ValidationError):
        await service.list_homeworks(actor(owner), limit=0)


async def test_get_missing_homework_is_404(service: HomeworkService, owner: User) -> None:
    with pytest.raises(NotFoundError) as raised:
        await service.get_homework(actor(owner), 999_999)
    assert raised.value.code == "homework_not_found"
