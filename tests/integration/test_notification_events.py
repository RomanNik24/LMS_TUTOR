"""События уведомлений в сервисах: кто, что и сколько раз получает (T5.06, docs/05 §6)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as aioredis
import time_machine
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkKind,
    NotificationType,
    UserRole,
)
from src.core.exceptions import BusinessRuleError
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.models import (
    Homework,
    HomeworkAssignment,
    Notification,
    StudentProfile,
    Subject,
    User,
)
from src.schemas.homework import (
    AssigneesAdd,
    GradeRequest,
    HomeworkCreate,
    ReturnRequest,
    SubmitRequest,
)
from src.schemas.schedule import LessonCancel, LessonCreate, LessonReschedule
from src.services.auth import AuthService
from src.services.expiry import ExpiryService
from src.services.grading import GradingService
from src.services.homework import HomeworkService
from src.services.schedule import ScheduleService
from src.services.submissions import SubmissionService

pytestmark = pytest.mark.security

NOW = datetime(2030, 10, 6, 12, 0, tzinfo=UTC)
FUTURE = NOW + timedelta(days=5)
BOT_TOKEN = "123:TEST"  # noqa: S105 - тестовый токен


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


async def make(db: AsyncSession, role: UserRole, name: str, tg: int, **extra: object) -> User:
    user = User(role=role, display_name=name, telegram_id=tg, **extra)
    db.add(user)
    await db.commit()
    return user


def actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await make(db_session, UserRole.OWNER, "Роман", 1)


@pytest.fixture
async def manager(db_session: AsyncSession) -> User:
    return await make(db_session, UserRole.MANAGER, "Мария", 2)


@pytest.fixture
async def retired(db_session: AsyncSession) -> User:
    return await make(db_session, UserRole.MANAGER, "Бывший", 3, is_active=False)


async def student(db: AsyncSession, name: str, tg: int, teacher: User) -> User:
    user = await make(db, UserRole.STUDENT, name, tg)
    db.add(StudentProfile(user_id=user.id, teacher_id=teacher.id, lesson_price=1000))
    await db.commit()
    return user


@pytest.fixture
async def anya(db_session: AsyncSession, owner: User) -> User:
    return await student(db_session, "Аня", 11, owner)


@pytest.fixture
async def boris(db_session: AsyncSession, owner: User) -> User:
    return await student(db_session, "Борис", 12, owner)


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add(Subject(code="informatics", name="Информатика"))
    await db_session.commit()


async def queued(db: AsyncSession, kind: NotificationType) -> list[Notification]:
    stmt = select(Notification).where(Notification.type == kind.value).order_by(Notification.id)
    return list((await db.execute(stmt)).scalars())


def regular(student_ids: list[int]) -> HomeworkCreate:
    return HomeworkCreate.model_validate(
        {
            "kind": "regular",
            "title": "Графы",
            "subject_code": "informatics",
            "max_score": 13,
            "due_mode": "fixed",
            "due_at": FUTURE,
            "student_ids": student_ids,
        }
    )


async def submitted_assignment(
    db: AsyncSession,
    owner: User,
    who: User,
    status: AssignmentStatus = AssignmentStatus.SUBMITTED,
    **patch: object,
) -> HomeworkAssignment:
    subject = (await db.execute(select(Subject).limit(1))).scalar_one()
    homework = Homework(
        created_by=owner.id,
        subject_id=subject.id,
        kind=HomeworkKind.REGULAR,
        title="Графы",
        max_score=13,
        due_mode=DueMode.FIXED,
    )
    db.add(homework)
    await db.flush()
    row = HomeworkAssignment(
        homework_id=homework.id,
        student_id=who.id,
        status=status,
        original_due_at=FUTURE,
        due_at=FUTURE,
        submitted_at=NOW - timedelta(hours=1),
        **patch,
    )
    db.add(row)
    await db.commit()
    return row


# ---------------------------------------------------------------- выдача ДЗ


async def test_homework_assignment_notifies_each_student_once(
    db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    service = HomeworkService(db_session)
    item = await service.create_homework(actor(owner), regular([anya.id, boris.id]))
    rows = await queued(db_session, NotificationType.HOMEWORK_ASSIGNED)
    assert {row.user_id for row in rows} == {anya.id, boris.id}
    assert all(row.is_urgent is False for row in rows)
    anya_row = next(row for row in rows if row.user_id == anya.id)
    assignment = next(a for a in item.assignments if a.student_id == anya.id)
    assert anya_row.payload == {
        "assignment_id": assignment.id,
        "title": "Графы",
        "due_epoch": int(FUTURE.timestamp()),
    }
    assert anya_row.dedup_key == f"homework_assigned:{assignment.id}"


async def test_adding_assignees_notifies_only_new_students(
    db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    service = HomeworkService(db_session)
    item = await service.create_homework(actor(owner), regular([anya.id]))
    await service.add_assignees(
        actor(owner), item.id, AssigneesAdd(student_ids=[anya.id, boris.id])
    )
    await service.add_assignees(
        actor(owner), item.id, AssigneesAdd(student_ids=[anya.id, boris.id])
    )
    rows = await queued(db_session, NotificationType.HOMEWORK_ASSIGNED)
    assert sorted(row.user_id for row in rows) == sorted([anya.id, boris.id])


# ---------------------------------------------------------------- оценка и возврат


async def test_grade_notifies_student_once_and_again_only_for_new_score(
    db_session: AsyncSession, owner: User, manager: User, anya: User
) -> None:
    row = await submitted_assignment(db_session, owner, anya)
    service = GradingService(db_session)
    await service.grade_assignment(actor(manager), row.id, GradeRequest(score=11))
    await service.grade_assignment(actor(manager), row.id, GradeRequest(score=11))
    (only,) = await queued(db_session, NotificationType.HOMEWORK_GRADED)
    assert only.user_id == anya.id
    assert only.payload["score"] == 11
    assert only.payload["max_score"] == 13
    await service.grade_assignment(actor(manager), row.id, GradeRequest(score=12))
    assert len(await queued(db_session, NotificationType.HOMEWORK_GRADED)) == 2


async def test_failed_grade_leaves_no_notification(
    db_session: AsyncSession, owner: User, manager: User, anya: User
) -> None:
    row = await submitted_assignment(db_session, owner, anya)
    with pytest.raises(BusinessRuleError):
        await GradingService(db_session).grade_assignment(
            actor(manager), row.id, GradeRequest(score=99)
        )
    assert await queued(db_session, NotificationType.HOMEWORK_GRADED) == []


async def test_return_notifies_student_with_comment_once(
    db_session: AsyncSession, owner: User, manager: User, anya: User
) -> None:
    row = await submitted_assignment(db_session, owner, anya)
    service = GradingService(db_session)
    await service.return_for_revision(
        actor(manager), row.id, ReturnRequest(comment="Исправь №3", new_due_at=FUTURE)
    )
    (note,) = await queued(db_session, NotificationType.HOMEWORK_RETURNED)
    assert note.user_id == anya.id
    assert note.payload["comment"] == "Исправь №3"
    # повторный возврат невозможен (работа уже не «сдана») и дубля не даёт
    with pytest.raises(BusinessRuleError):
        await service.return_for_revision(
            actor(manager), row.id, ReturnRequest(comment="Ещё раз", new_due_at=FUTURE)
        )
    assert len(await queued(db_session, NotificationType.HOMEWORK_RETURNED)) == 1


# ---------------------------------------------------------------- сдача и сгорание


async def test_submission_notifies_active_staff_only(
    db_session: AsyncSession, owner: User, manager: User, retired: User, anya: User
) -> None:
    row = await submitted_assignment(db_session, owner, anya, status=AssignmentStatus.ASSIGNED)
    await SubmissionService(db_session).submit_self_reported(
        actor(anya), row.id, SubmitRequest(student_comment=None)
    )
    rows = await queued(db_session, NotificationType.HOMEWORK_SUBMITTED)
    assert {note.user_id for note in rows} == {owner.id, manager.id}
    assert retired.id not in {note.user_id for note in rows}
    assert rows[0].payload["student_name"] == "Аня"
    assert rows[0].payload["title"] == "Графы"
    assert all(note.is_urgent is False for note in rows)


async def test_expiry_notifies_staff_once_per_assignment(
    db_session: AsyncSession, owner: User, manager: User, anya: User
) -> None:
    row = await submitted_assignment(
        db_session, owner, anya, status=AssignmentStatus.ASSIGNED, extensions_count=2
    )
    await db_session.execute(
        update(HomeworkAssignment)
        .where(HomeworkAssignment.id == row.id)
        .values(due_at=NOW - timedelta(hours=1))
    )
    await db_session.commit()
    service = ExpiryService(db_session)
    assert (await service.expire_due_assignments()).expired == 1
    assert (await service.expire_due_assignments()).expired == 0
    rows = await queued(db_session, NotificationType.HOMEWORK_EXPIRED)
    assert {note.user_id for note in rows} == {owner.id, manager.id}
    assert len(rows) == 2


# ---------------------------------------------------------------- уроки


def lesson_data(student_ids: list[int], start: datetime) -> LessonCreate:
    return LessonCreate.model_validate(
        {
            "subject_code": "informatics",
            "student_ids": student_ids,
            "start_at": start,
            "end_at": start + timedelta(hours=1),
        }
    )


async def test_cancel_notifies_every_participant_and_marks_urgency(
    db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    service = ScheduleService(db_session)
    soon = await service.create_lesson(
        actor(owner), lesson_data([anya.id, boris.id], NOW + timedelta(hours=5))
    )
    later = await service.create_lesson(
        actor(owner), lesson_data([anya.id], NOW + timedelta(days=3))
    )
    await service.cancel_lesson(actor(owner), soon.id, LessonCancel())
    await service.cancel_lesson(actor(owner), later.id, LessonCancel())
    rows = await queued(db_session, NotificationType.LESSON_CANCELLED)
    urgent = {(row.user_id, row.is_urgent) for row in rows}
    assert urgent == {(anya.id, True), (boris.id, True), (anya.id, False)}
    assert len(rows) == 3
    # повторная отмена невозможна и дубля не создаёт
    with pytest.raises(BusinessRuleError):
        await service.cancel_lesson(actor(owner), soon.id, LessonCancel())
    assert len(await queued(db_session, NotificationType.LESSON_CANCELLED)) == 3


async def test_reschedule_notifies_participants_and_is_urgent_by_old_or_new_time(
    db_session: AsyncSession, owner: User, anya: User
) -> None:
    service = ScheduleService(db_session)
    far = NOW + timedelta(days=3)
    item = await service.create_lesson(actor(owner), lesson_data([anya.id], far))
    new_start = NOW + timedelta(hours=2)  # перенос на ближайшие часы
    await service.reschedule_lesson(
        actor(owner),
        item.id,
        LessonReschedule(start_at=new_start, end_at=new_start + timedelta(hours=1)),
    )
    (note,) = await queued(db_session, NotificationType.LESSON_RESCHEDULED)
    assert note.user_id == anya.id
    assert note.is_urgent is True
    assert note.payload["old_start_epoch"] == int(far.timestamp())
    assert note.payload["new_start_epoch"] == int(new_start.timestamp())
    # обе даты далеко: несрочно
    other = await service.create_lesson(
        actor(owner), lesson_data([anya.id], NOW + timedelta(days=4))
    )
    moved = NOW + timedelta(days=5)
    await service.reschedule_lesson(
        actor(owner), other.id, LessonReschedule(start_at=moved, end_at=moved + timedelta(hours=1))
    )
    second = (await queued(db_session, NotificationType.LESSON_RESCHEDULED))[1]
    assert second.is_urgent is False


# ---------------------------------------------------------------- приглашение


@pytest.fixture
async def redis_clean(redis_client: aioredis.Redis) -> aioredis.Redis:
    await redis_client.flushdb()
    return redis_client


async def test_student_accepting_invite_notifies_staff_once(
    db_session: AsyncSession,
    redis_clean: aioredis.Redis,
    owner: User,
    manager: User,
    retired: User,
) -> None:
    pupil = await make(db_session, UserRole.STUDENT, "Вера", 0)
    pupil.telegram_id = None
    db_session.add(StudentProfile(user_id=pupil.id, teacher_id=owner.id))
    await db_session.commit()
    auth = AuthService(db_session, SessionStore(redis_clean), RateLimiter(redis_clean), BOT_TOKEN)
    issued = await auth.create_invite(actor(owner), pupil.id)
    await auth.accept_invite(issued.token, 555)
    rows = await queued(db_session, NotificationType.STUDENT_JOINED)
    assert {row.user_id for row in rows} == {owner.id, manager.id}
    assert rows[0].payload == {"student_id": pupil.id, "student_name": "Вера"}


async def test_staff_accepting_invite_and_relink_do_not_notify(
    db_session: AsyncSession, redis_clean: aioredis.Redis, owner: User, manager: User, anya: User
) -> None:
    owner_actor = actor(owner)
    manager_id, anya_id = manager.id, anya.id
    auth = AuthService(db_session, SessionStore(redis_clean), RateLimiter(redis_clean), BOT_TOKEN)
    staff_invite = await auth.create_invite(owner_actor, manager_id)
    # у сотрудника и ученика уже есть Telegram: это перепривязка, а не вступление
    await auth.confirm_relink(staff_invite.token, 777)
    relink = await auth.create_invite(owner_actor, anya_id)
    await auth.confirm_relink(relink.token, 888)
    assert await queued(db_session, NotificationType.STUDENT_JOINED) == []


# ---------------------------------------------------------------- контракт с рендерером


async def test_every_event_payload_can_be_rendered(
    db_session: AsyncSession, owner: User, manager: User, anya: User
) -> None:
    """Поля payload, которые кладут сервисы, совпадают с тем, что читает NotificationRenderer."""
    from src.services.notification_render import NotificationRenderer  # noqa: PLC0415

    owner_actor, manager_actor = actor(owner), actor(manager)
    homeworks = HomeworkService(db_session)
    await homeworks.create_homework(owner_actor, regular([anya.id]))
    row = await submitted_assignment(db_session, owner, anya, status=AssignmentStatus.ASSIGNED)
    await SubmissionService(db_session).submit_self_reported(
        actor(anya), row.id, SubmitRequest(student_comment=None)
    )
    grading = GradingService(db_session)
    await grading.return_for_revision(
        manager_actor, row.id, ReturnRequest(comment="Исправь", new_due_at=FUTURE)
    )
    graded = await submitted_assignment(db_session, owner, anya)
    await grading.grade_assignment(manager_actor, graded.id, GradeRequest(score=5))
    schedule = ScheduleService(db_session)
    first = await schedule.create_lesson(
        owner_actor, lesson_data([anya.id], NOW + timedelta(days=2))
    )
    await schedule.reschedule_lesson(
        owner_actor,
        first.id,
        LessonReschedule(start_at=NOW + timedelta(days=3), end_at=NOW + timedelta(days=3, hours=1)),
    )
    await schedule.cancel_lesson(owner_actor, first.id, LessonCancel())
    expired = await submitted_assignment(
        db_session, owner, anya, status=AssignmentStatus.ASSIGNED, extensions_count=2
    )
    await db_session.execute(
        update(HomeworkAssignment)
        .where(HomeworkAssignment.id == expired.id)
        .values(due_at=NOW - timedelta(hours=1))
    )
    await db_session.commit()
    await ExpiryService(db_session).expire_due_assignments()

    renderer = NotificationRenderer("https://lms.example.com")
    notes = list((await db_session.execute(select(Notification))).scalars())
    kinds = {note.type for note in notes}
    assert {
        "homework_assigned",
        "homework_returned",
        "homework_graded",
        "homework_submitted",
        "homework_expired",
        "lesson_rescheduled",
        "lesson_cancelled",
    } <= kinds
    for note in notes:
        recipient = (
            await db_session.execute(select(User).where(User.id == note.user_id))
        ).scalar_one()
        assert renderer.render(note, recipient).text
