"""Периодические задачи этапа 5 на реальной PostgreSQL (T5.05, docs/03 §9, docs/05 §6)."""

import importlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import time_machine
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import (
    AssignmentStatus,
    AuthTokenPurpose,
    DueMode,
    HomeworkKind,
    LessonStatus,
    NotificationType,
    UserRole,
)
from src.db.models import (
    AuthToken,
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    Notification,
    StudentProfile,
    Subject,
    User,
)
from src.services.maintenance import MaintenanceService
from src.services.notification_dispatch import NotificationDispatcher
from src.services.notification_render import NotificationRenderer
from src.services.reminders import ReminderService

START = datetime(2030, 10, 14, 14, 0, tzinfo=UTC)
BASE = "https://lms.example.com"


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send(self, telegram_id: int, message: object) -> None:
        self.sent.append((telegram_id, getattr(message, "text", "")))


async def user(
    db: AsyncSession, name: str, role: UserRole, telegram_id: int, **extra: object
) -> User:
    item = User(
        role=role, display_name=name, telegram_id=telegram_id, timezone="Europe/Moscow", **extra
    )
    db.add(item)
    await db.flush()
    return item


@pytest.fixture
async def teacher(db_session: AsyncSession) -> User:
    return await user(db_session, "Роман", UserRole.OWNER, 7000)


@pytest.fixture
async def anya(db_session: AsyncSession) -> User:
    item = await user(db_session, "Аня", UserRole.STUDENT, 7001)
    db_session.add(
        StudentProfile(
            user_id=item.id,
            teacher_id=item.id,
            lesson_price=1000,
            video_url="https://telemost.example/anya",
            board_url="https://board.example/anya",
        )
    )
    await db_session.flush()
    return item


@pytest.fixture
async def subject(db_session: AsyncSession) -> Subject:
    item = Subject(code="informatics", name="Информатика")
    existing = (
        await db_session.execute(select(Subject).where(Subject.code == "informatics"))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    db_session.add(item)
    await db_session.flush()
    return item


async def lesson(
    db: AsyncSession,
    teacher: User,
    subject: Subject,
    students: list[User],
    start: datetime = START,
    **extra: object,
) -> Lesson:
    item = Lesson(
        teacher_id=teacher.id,
        subject_id=subject.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
        **extra,
    )
    db.add(item)
    await db.flush()
    for student in students:
        db.add(LessonParticipant(lesson_id=item.id, student_id=student.id))
    await db.flush()
    return item


async def queued(db: AsyncSession, kind: NotificationType) -> list[Notification]:
    stmt = select(Notification).where(Notification.type == kind.value).order_by(Notification.id)
    return list((await db.execute(stmt)).scalars())


# ---------------------------------------------------------------- напоминание об уроке


async def test_lesson_reminder_is_queued_for_exactly_30_minutes_before(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    item = await lesson(db_session, teacher, subject, [anya])
    service = ReminderService(db_session)
    assert await service.generate_lesson_reminders(START - timedelta(minutes=40)) == 0
    assert await service.generate_lesson_reminders(START - timedelta(minutes=31)) == 1
    (row,) = await queued(db_session, NotificationType.LESSON_REMINDER)
    assert row.user_id == anya.id
    assert row.scheduled_for == START - timedelta(minutes=30)
    assert row.is_urgent is True
    assert row.dedup_key == f"lesson_reminder:{item.id}:{anya.id}:{int(START.timestamp())}"
    assert row.payload["video_url"] == "https://telemost.example/anya"
    assert row.payload["subject"] == "Информатика"


async def test_lesson_reminder_not_duplicated_on_restart(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    await lesson(db_session, teacher, subject, [anya])
    service = ReminderService(db_session)
    now = START - timedelta(minutes=30)
    assert await service.generate_lesson_reminders(now) == 1
    # перезапуск воркера и повторные тики в течение окна
    assert await service.generate_lesson_reminders(now) == 0
    assert await service.generate_lesson_reminders(now + timedelta(minutes=1)) == 0
    assert len(await queued(db_session, NotificationType.LESSON_REMINDER)) == 1


async def test_lesson_reminder_uses_current_time_with_time_machine(
    db_session: AsyncSession,
    teacher: User,
    anya: User,
    subject: Subject,
) -> None:
    await lesson(db_session, teacher, subject, [anya])
    with time_machine.travel(START - timedelta(minutes=45), tick=False):
        assert await ReminderService(db_session).generate_lesson_reminders() == 0
    with time_machine.travel(START - timedelta(minutes=30), tick=False):
        assert await ReminderService(db_session).generate_lesson_reminders() == 1


async def test_late_start_of_worker_still_reminds_but_not_too_late(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    await lesson(db_session, teacher, subject, [anya])
    service = ReminderService(db_session)
    assert await service.generate_lesson_reminders(START - timedelta(minutes=26)) == 1
    other = await lesson(db_session, teacher, subject, [anya], START + timedelta(days=1))
    # до урока осталось 20 минут: «через 30 минут» было бы неправдой
    assert await service.generate_lesson_reminders(other.start_at - timedelta(minutes=20)) == 0


async def test_rescheduled_lesson_gets_new_reminder_and_old_one_is_dropped(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    item = await lesson(db_session, teacher, subject, [anya])
    service = ReminderService(db_session)
    await service.generate_lesson_reminders(START - timedelta(minutes=31))
    new_start = START + timedelta(hours=3)
    item.start_at = new_start
    item.end_at = new_start + timedelta(hours=1)
    await db_session.flush()
    assert await service.generate_lesson_reminders(new_start - timedelta(minutes=31)) == 1
    old, new = await queued(db_session, NotificationType.LESSON_REMINDER)
    assert old.dedup_key != new.dedup_key
    # диспетчер отправляет только актуальное напоминание
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(
        db_session, notifier, NotificationRenderer(BASE), pause_seconds=0
    )
    stats = await dispatcher.dispatch_due(new_start - timedelta(minutes=30))
    assert (stats.sent, stats.skipped) == (1, 1)
    assert "Через 30 минут" in notifier.sent[0][1]


async def test_lesson_reminder_skips_cancelled_archived_and_serves_groups(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    boris = await user(db_session, "Борис", UserRole.STUDENT, 7002)
    gone = await user(db_session, "Архив", UserRole.STUDENT, 7003, is_active=False)
    await lesson(db_session, teacher, subject, [anya, boris, gone])
    await lesson(
        db_session,
        teacher,
        subject,
        [anya],
        START + timedelta(minutes=5),
        status=LessonStatus.CANCELLED,
    )
    created = await ReminderService(db_session).generate_lesson_reminders(
        START - timedelta(minutes=30)
    )
    assert created == 2
    rows = await queued(db_session, NotificationType.LESSON_REMINDER)
    assert {row.user_id for row in rows} == {anya.id, boris.id}
    boris_row = next(row for row in rows if row.user_id == boris.id)
    assert boris_row.payload["video_url"] is None  # у Бориса нет профиля со ссылками


async def test_lesson_own_links_override_profile(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    await lesson(
        db_session, teacher, subject, [anya], video_url_override="https://telemost.example/lesson"
    )
    await ReminderService(db_session).generate_lesson_reminders(START - timedelta(minutes=30))
    (row,) = await queued(db_session, NotificationType.LESSON_REMINDER)
    assert row.payload["video_url"] == "https://telemost.example/lesson"
    assert row.payload["board_url"] == "https://board.example/anya"


# ---------------------------------------------------------------- дедлайн ДЗ


async def assignment(
    db: AsyncSession,
    teacher: User,
    subject: Subject,
    student: User,
    due: datetime,
    created_at: datetime,
    **extra: object,
) -> HomeworkAssignment:
    homework = Homework(
        created_by=teacher.id,
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
        student_id=student.id,
        original_due_at=due,
        due_at=due,
        created_at=created_at,
        **extra,
    )
    db.add(row)
    await db.flush()
    return row


DUE = datetime(2030, 10, 20, 17, 0, tzinfo=UTC)


async def test_homework_reminder_24_hours_before_deadline(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    row = await assignment(db_session, teacher, subject, anya, DUE, DUE - timedelta(days=5))
    service = ReminderService(db_session)
    assert await service.generate_homework_reminders(DUE - timedelta(hours=26)) == 0
    assert await service.generate_homework_reminders(DUE - timedelta(hours=24, minutes=2)) == 1
    (note,) = await queued(db_session, NotificationType.HOMEWORK_DEADLINE)
    assert note.scheduled_for == DUE - timedelta(hours=24)
    assert note.is_urgent is False
    assert note.dedup_key == f"homework_deadline:{row.id}:{int(DUE.timestamp())}"
    # повтор после перезапуска ничего не добавляет
    assert await service.generate_homework_reminders(DUE - timedelta(hours=23, minutes=58)) == 0
    assert len(await queued(db_session, NotificationType.HOMEWORK_DEADLINE)) == 1


async def test_homework_reminder_skips_late_assigned_and_finished(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    # выдано за 10 часов до срока: «завтра дедлайн» было бы неправдой
    await assignment(db_session, teacher, subject, anya, DUE, DUE - timedelta(hours=10))
    boris = await user(db_session, "Борис", UserRole.STUDENT, 7002)
    await assignment(
        db_session,
        teacher,
        subject,
        boris,
        DUE,
        DUE - timedelta(days=5),
        status=AssignmentStatus.SUBMITTED,
    )
    created = await ReminderService(db_session).generate_homework_reminders(
        DUE - timedelta(hours=24)
    )
    assert created == 0


async def test_extension_creates_new_homework_reminder(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    row = await assignment(db_session, teacher, subject, anya, DUE, DUE - timedelta(days=5))
    service = ReminderService(db_session)
    await service.generate_homework_reminders(DUE - timedelta(hours=24))
    new_due = DUE + timedelta(days=3)
    row.due_at = new_due
    row.extensions_count = 1
    await db_session.flush()
    assert await service.generate_homework_reminders(new_due - timedelta(hours=24)) == 1
    old, new = await queued(db_session, NotificationType.HOMEWORK_DEADLINE)
    assert old.dedup_key != new.dedup_key
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(
        db_session, notifier, NotificationRenderer(BASE), pause_seconds=0
    )
    stats = await dispatcher.dispatch_due(new_due - timedelta(hours=24))
    assert (stats.sent, stats.skipped) == (1, 1)  # старое напоминание устарело


# ---------------------------------------------------------------- уроки без отметки


async def test_unmarked_lesson_reminder_after_one_hour(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    item = await lesson(db_session, teacher, subject, [anya])
    end = item.end_at
    service = ReminderService(db_session)
    assert await service.notify_unmarked_lessons(end + timedelta(minutes=59)) == 0
    assert await service.notify_unmarked_lessons(end + timedelta(hours=1)) == 1
    (row,) = await queued(db_session, NotificationType.LESSON_UNMARKED)
    assert row.user_id == teacher.id
    assert row.dedup_key == f"lesson_unmarked:{item.id}:{teacher.id}"
    assert await service.notify_unmarked_lessons(end + timedelta(hours=2)) == 0


async def test_unmarked_skips_marked_cancelled_and_old_lessons(
    db_session: AsyncSession, teacher: User, anya: User, subject: Subject
) -> None:
    await lesson(db_session, teacher, subject, [anya], status=LessonStatus.COMPLETED)
    await lesson(
        db_session,
        teacher,
        subject,
        [anya],
        START + timedelta(days=1),
        status=LessonStatus.CANCELLED,
    )
    await lesson(db_session, teacher, subject, [anya], START - timedelta(days=60))
    now = START + timedelta(days=2)
    assert await ReminderService(db_session).notify_unmarked_lessons(now) == 0


# ---------------------------------------------------------------- уборка токенов


async def test_cleanup_tokens_removes_only_long_expired(
    db_session: AsyncSession, teacher: User
) -> None:
    now = datetime(2030, 10, 14, 3, 30, tzinfo=UTC)
    for index, delta in enumerate(
        [timedelta(days=-3), timedelta(hours=-25), timedelta(hours=-1), timedelta(days=2)]
    ):
        db_session.add(
            AuthToken(
                purpose=AuthTokenPurpose.WEB_LOGIN,
                user_id=teacher.id,
                token_hash=f"hash-{index}".ljust(64, "0"),
                expires_at=now + delta,
            )
        )
    await db_session.flush()
    assert await MaintenanceService(db_session).cleanup_tokens(now) == 2
    left = (await db_session.execute(select(AuthToken.token_hash))).scalars().all()
    assert sorted(item[:6] for item in left) == ["hash-2", "hash-3"]
    assert await MaintenanceService(db_session).cleanup_tokens(now) == 0


# ---------------------------------------------------------------- задачи воркера


@pytest.fixture
def tasks(app_settings_env: None) -> SimpleNamespace:  # noqa: ARG001
    from src.worker import broker as broker_module  # noqa: PLC0415
    from src.worker import tasks as tasks_module  # noqa: PLC0415

    importlib.reload(broker_module)
    importlib.reload(tasks_module)
    return SimpleNamespace(module=tasks_module)


def test_every_periodic_task_has_its_schedule(tasks: SimpleNamespace) -> None:
    expected = {
        "heartbeat": "*/5 * * * *",
        "dispatch_due_notifications": "* * * * *",
        "generate_lesson_reminders": "* * * * *",
        "generate_homework_reminders": "*/5 * * * *",
        "expire_homework_assignments": "*/5 * * * *",
        "notify_unmarked_lessons": "*/15 * * * *",
        "generate_scheduled_lessons": "0 3 * * *",
        "cleanup_tokens": "30 3 * * *",
        "send_morning_digest": "0 * * * *",
    }
    scheduled = {
        task.task_name: task.labels["schedule"][0]["cron"]
        for task in vars(tasks.module).values()
        if hasattr(task, "task_name") and "schedule" in getattr(task, "labels", {})
    }
    assert scheduled == expected


async def test_dispatch_task_without_bot_does_nothing(
    db_session: AsyncSession, tasks: SimpleNamespace
) -> None:
    context = SimpleNamespace(
        state={"bot": None, "settings": SimpleNamespace(public_base_url=BASE)}
    )
    assert await tasks.module.dispatch_due_notifications.original_func(context, db_session) == 0


async def test_dispatch_task_sends_through_bot(
    db_session: AsyncSession,
    tasks: SimpleNamespace,
    anya: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = FakeNotifier()
    monkeypatch.setattr(tasks.module, "TelegramNotifier", lambda bot: notifier)
    db_session.add(
        Notification(
            user_id=anya.id,
            type=NotificationType.STUDENT_JOINED.value,
            payload={"student_id": 1, "student_name": "Борис"},
            dedup_key="joined",
            scheduled_for=datetime(2020, 1, 1, 9, 0, tzinfo=UTC),
            is_urgent=True,
        )
    )
    await db_session.flush()
    context = SimpleNamespace(
        state={"bot": object(), "settings": SimpleNamespace(public_base_url=BASE)}
    )
    assert await tasks.module.dispatch_due_notifications.original_func(context, db_session) == 1
    assert notifier.sent == [(7001, "👋 Подключение: Борис.")]


async def test_expire_and_generation_tasks_run_on_empty_database(
    db_session: AsyncSession, tasks: SimpleNamespace
) -> None:
    assert await tasks.module.expire_homework_assignments.original_func(db_session) == 0
    assert await tasks.module.cleanup_tokens.original_func(db_session) == 0
    assert await tasks.module.generate_lesson_reminders.original_func(db_session) == 0
    assert await tasks.module.generate_homework_reminders.original_func(db_session) == 0
    assert await tasks.module.notify_unmarked_lessons.original_func(db_session) == 0
    assert await tasks.module.send_morning_digest.original_func(db_session) == 0
    context = SimpleNamespace(state={"settings": SimpleNamespace(schedule_horizon_weeks=2)})
    assert await tasks.module.generate_scheduled_lessons.original_func(context, db_session) == 0


async def test_expire_task_moves_overdue_assignment_to_expired(
    db_session: AsyncSession, tasks: SimpleNamespace, teacher: User, anya: User, subject: Subject
) -> None:
    past = datetime(2020, 1, 10, 12, 0, tzinfo=UTC)
    row = await assignment(db_session, teacher, subject, anya, past, past - timedelta(days=5))
    await db_session.execute(
        update(HomeworkAssignment).where(HomeworkAssignment.id == row.id).values(extensions_count=2)
    )
    assert await tasks.module.expire_homework_assignments.original_func(db_session) == 1
    await db_session.refresh(row)
    assert row.status == AssignmentStatus.EXPIRED
