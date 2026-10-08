"""Очередь и диспетчер уведомлений на реальной PostgreSQL (T5.03, docs/05 §6)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkKind,
    LessonStatus,
    NotificationStatus,
    NotificationType,
    UserRole,
)
from src.db.models import (
    Homework,
    HomeworkAssignment,
    Lesson,
    Notification,
    Subject,
    User,
)
from src.services.notification_dispatch import NotificationDispatcher
from src.services.notification_render import NotificationRenderer
from src.services.notifications import NotificationService
from src.services.notifier import (
    NotifierBlockedError,
    NotifierTemporaryError,
    OutgoingMessage,
)

BASE = "https://lms.example.com"
# 14 октября 2030, 09:00 UTC = 12:00 по Москве (день)
DAY = datetime(2030, 10, 14, 9, 0, tzinfo=UTC)
# 20:00 UTC = 23:00 по Москве (тихие часы)
NIGHT = datetime(2030, 10, 14, 20, 0, tzinfo=UTC)
LESSON_START = datetime(2030, 10, 14, 14, 30, tzinfo=UTC)


class FakeNotifier:
    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.sent: list[tuple[int, str]] = []

    async def send(self, telegram_id: int, message: OutgoingMessage) -> None:
        if self.errors:
            raise self.errors.pop(0)
        self.sent.append((telegram_id, message.text))


def dispatcher(db: AsyncSession, notifier: FakeNotifier) -> NotificationDispatcher:
    return NotificationDispatcher(db, notifier, NotificationRenderer(BASE), pause_seconds=0)


async def make_user(
    db: AsyncSession, name: str = "Аня", telegram_id: int = 501, **extra: object
) -> User:
    user = User(
        role=UserRole.STUDENT,
        display_name=name,
        telegram_id=telegram_id,
        timezone="Europe/Moscow",
        **extra,
    )
    db.add(user)
    await db.flush()
    return user


async def queue(
    db: AsyncSession,
    user: User,
    kind: NotificationType,
    payload: dict[str, object],
    key: str,
    *,
    scheduled_for: datetime | None = None,
    is_urgent: bool = False,
) -> bool:
    created = await NotificationService(db).enqueue(
        user.id, kind, payload, key, scheduled_for=scheduled_for, is_urgent=is_urgent
    )
    await db.flush()
    return created


def graded(assignment_id: int = 1) -> dict[str, object]:
    return {
        "assignment_id": assignment_id,
        "title": f"Графы {assignment_id}",
        "score": 11,
        "max_score": 13,
    }


async def rows(db: AsyncSession) -> list[Notification]:
    db.expire_all()
    return list((await db.execute(select(Notification).order_by(Notification.id))).scalars())


# ---------------------------------------------------------------- очередь


async def test_enqueue_is_idempotent_by_dedup_key(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    first = await queue(db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "same")
    second = await queue(db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "same")
    assert (first, second) == (True, False)
    assert len(await rows(db_session)) == 1


async def test_enqueue_does_not_commit(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await queue(db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "k")
    await db_session.rollback()
    assert await rows(db_session) == []


# ---------------------------------------------------------------- отправка


async def test_due_notification_is_sent_and_future_one_waits(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await queue(
        db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "now", scheduled_for=DAY
    )
    await queue(
        db_session,
        user,
        NotificationType.HOMEWORK_GRADED,
        graded(2),
        "later",
        scheduled_for=DAY + timedelta(hours=1),
    )
    notifier = FakeNotifier()
    stats = await dispatcher(db_session, notifier).dispatch_due(DAY)
    assert (stats.sent, stats.total) == (1, 1)
    assert notifier.sent == [(501, "✅ ДЗ «Графы 1» проверено: 11 из 13.")]
    first, second = await rows(db_session)
    assert (first.status, first.attempts, first.sent_at) == (NotificationStatus.SENT, 1, DAY)
    assert second.status == NotificationStatus.PENDING


async def test_rerun_does_not_send_again(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await queue(
        db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "k", scheduled_for=DAY
    )
    notifier = FakeNotifier()
    await dispatcher(db_session, notifier).dispatch_due(DAY)
    again = await dispatcher(db_session, notifier).dispatch_due(DAY)
    assert again.total == 0
    assert len(notifier.sent) == 1


async def test_many_notifications_go_in_several_batches(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    for number in range(60):
        await queue(
            db_session,
            user,
            NotificationType.HOMEWORK_GRADED,
            graded(number + 1),
            f"k{number}",
            scheduled_for=DAY,
        )
    notifier = FakeNotifier()
    stats = await dispatcher(db_session, notifier).dispatch_due(DAY)
    assert stats.sent == 60
    assert len(notifier.sent) == 60


# ---------------------------------------------------------------- тихие часы и срочность


async def test_quiet_hours_defer_non_urgent_until_8_local(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await queue(
        db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "k", scheduled_for=NIGHT
    )
    notifier = FakeNotifier()
    stats = await dispatcher(db_session, notifier).dispatch_due(NIGHT)
    assert (stats.deferred, stats.sent) == (1, 0)
    (row,) = await rows(db_session)
    assert row.status == NotificationStatus.PENDING
    assert row.scheduled_for == datetime(2030, 10, 15, 5, 0, tzinfo=UTC)  # 08:00 по Москве
    # утром уходит
    morning = await dispatcher(db_session, notifier).dispatch_due(row.scheduled_for)
    assert morning.sent == 1


async def test_urgent_notification_ignores_quiet_hours(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await queue(
        db_session,
        user,
        NotificationType.HOMEWORK_GRADED,
        graded(),
        "k",
        scheduled_for=NIGHT,
        is_urgent=True,
    )
    notifier = FakeNotifier()
    stats = await dispatcher(db_session, notifier).dispatch_due(NIGHT)
    assert stats.sent == 1


# ---------------------------------------------------------------- актуальность


async def lesson(db: AsyncSession, teacher: User, **extra: object) -> Lesson:
    subject = Subject(code="info_t503", name="Информатика")
    db.add(subject)
    await db.flush()
    item = Lesson(
        teacher_id=teacher.id,
        subject_id=subject.id,
        start_at=LESSON_START,
        end_at=LESSON_START + timedelta(hours=1),
        **extra,
    )
    db.add(item)
    await db.flush()
    return item


def reminder(lesson_id: int, start: datetime = LESSON_START) -> dict[str, object]:
    return {
        "lesson_id": lesson_id,
        "start_epoch": int(start.timestamp()),
        "subject": "Информатика",
    }


async def test_reminder_is_sent_for_scheduled_lesson(db_session: AsyncSession) -> None:
    teacher = await make_user(db_session, "Роман", 700)
    student = await make_user(db_session)
    item = await lesson(db_session, teacher)
    await queue(
        db_session,
        student,
        NotificationType.LESSON_REMINDER,
        reminder(item.id),
        "r",
        scheduled_for=DAY,
        is_urgent=True,
    )
    stats = await dispatcher(db_session, FakeNotifier()).dispatch_due(DAY)
    assert stats.sent == 1


async def test_reminder_for_cancelled_lesson_is_skipped(db_session: AsyncSession) -> None:
    teacher = await make_user(db_session, "Роман", 700)
    student = await make_user(db_session)
    item = await lesson(db_session, teacher, status=LessonStatus.CANCELLED)
    await queue(
        db_session,
        student,
        NotificationType.LESSON_REMINDER,
        reminder(item.id),
        "r",
        scheduled_for=DAY,
    )
    notifier = FakeNotifier()
    stats = await dispatcher(db_session, notifier).dispatch_due(DAY)
    assert (stats.skipped, stats.sent) == (1, 0)
    assert notifier.sent == []
    (row,) = await rows(db_session)
    assert (row.status, row.last_error) == (NotificationStatus.SKIPPED, "stale")


async def test_reminder_for_rescheduled_lesson_is_skipped(db_session: AsyncSession) -> None:
    teacher = await make_user(db_session, "Роман", 700)
    student = await make_user(db_session)
    item = await lesson(db_session, teacher)
    old_payload = reminder(item.id, LESSON_START - timedelta(hours=2))  # старое время
    await queue(
        db_session,
        student,
        NotificationType.LESSON_REMINDER,
        old_payload,
        "old",
        scheduled_for=DAY,
    )
    await queue(
        db_session,
        student,
        NotificationType.LESSON_REMINDER,
        reminder(item.id),
        "new",
        scheduled_for=DAY,
    )
    notifier = FakeNotifier()
    stats = await dispatcher(db_session, notifier).dispatch_due(DAY)
    assert (stats.skipped, stats.sent) == (1, 1)


async def test_deadline_reminder_skipped_after_submission(db_session: AsyncSession) -> None:
    teacher = await make_user(db_session, "Роман", 700)
    student = await make_user(db_session)
    subject = Subject(code="info_t503b", name="Информатика")
    db_session.add(subject)
    await db_session.flush()
    homework = Homework(
        created_by=teacher.id,
        subject_id=subject.id,
        kind=HomeworkKind.REGULAR,
        title="Графы",
        max_score=13,
        due_mode=DueMode.FIXED,
    )
    db_session.add(homework)
    await db_session.flush()
    due = DAY + timedelta(hours=24)
    assignment = HomeworkAssignment(
        homework_id=homework.id, student_id=student.id, original_due_at=due, due_at=due
    )
    db_session.add(assignment)
    await db_session.flush()
    payload = {"assignment_id": assignment.id, "due_epoch": int(due.timestamp()), "title": "Графы"}
    await queue(
        db_session, student, NotificationType.HOMEWORK_DEADLINE, payload, "d1", scheduled_for=DAY
    )
    notifier = FakeNotifier()
    assert (await dispatcher(db_session, notifier).dispatch_due(DAY)).sent == 1
    await db_session.refresh(student)  # диспетчер завершает транзакцию и сбрасывает состояние
    await queue(
        db_session, student, NotificationType.HOMEWORK_DEADLINE, payload, "d2", scheduled_for=DAY
    )
    await db_session.refresh(assignment)  # диспетчер завершает транзакцию и сбрасывает состояние
    assignment.status = AssignmentStatus.SUBMITTED
    await db_session.flush()
    stats = await dispatcher(db_session, notifier).dispatch_due(DAY)
    assert (stats.skipped, stats.sent) == (1, 0)


# ---------------------------------------------------------------- сбои доставки


async def test_blocked_bot_marks_user_and_skips(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await queue(
        db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "k", scheduled_for=DAY
    )
    stats = await dispatcher(db_session, FakeNotifier(NotifierBlockedError("x"))).dispatch_due(DAY)
    assert stats.skipped == 1
    await db_session.refresh(user)
    assert user.bot_blocked is True
    (row,) = await rows(db_session)
    assert row.status == NotificationStatus.SKIPPED


async def test_network_error_is_retried_in_a_minute(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await queue(
        db_session, user, NotificationType.HOMEWORK_GRADED, graded(), "k", scheduled_for=DAY
    )
    notifier = FakeNotifier(NotifierTemporaryError("net"))
    stats = await dispatcher(db_session, notifier).dispatch_due(DAY)
    assert stats.retried == 1
    (row,) = await rows(db_session)
    assert row.status == NotificationStatus.PENDING
    retry_at = row.scheduled_for
    assert retry_at == DAY + timedelta(minutes=1)
    # раньше срока не уходит, в срок — уходит
    assert (await dispatcher(db_session, notifier).dispatch_due(DAY)).total == 0
    assert (await dispatcher(db_session, notifier).dispatch_due(retry_at)).sent == 1


async def test_archived_user_and_bad_payload(db_session: AsyncSession) -> None:
    gone = await make_user(db_session, "Архив", 601, is_active=False)
    user = await make_user(db_session)
    await queue(
        db_session, gone, NotificationType.HOMEWORK_GRADED, graded(), "a", scheduled_for=DAY
    )
    await queue(
        db_session,
        user,
        NotificationType.HOMEWORK_GRADED,
        {"assignment_id": 1},
        "b",
        scheduled_for=DAY,
    )
    stats = await dispatcher(db_session, FakeNotifier()).dispatch_due(DAY)
    assert (stats.skipped, stats.failed) == (1, 1)
    archived, broken = await rows(db_session)
    assert archived.status == NotificationStatus.SKIPPED
    assert (broken.status, broken.last_error) == (
        NotificationStatus.FAILED,
        "bad_notification_payload",
    )


# ---------------------------------------------------------------- параллельный запуск


class SlowNotifier(FakeNotifier):
    async def send(self, telegram_id: int, message: OutgoingMessage) -> None:
        await asyncio.sleep(0.01)
        await super().send(telegram_id, message)


@pytest.fixture
async def committed(migrated_postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_postgres_url, pool_size=4)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with factory() as session:
            await session.execute(delete(User).where(User.telegram_id == 9001))
            await session.commit()
        await engine.dispose()


async def test_two_dispatchers_in_parallel_never_send_twice(
    committed: async_sessionmaker[AsyncSession],
) -> None:
    async with committed() as setup:
        user = User(role=UserRole.STUDENT, display_name="Параллель", telegram_id=9001)
        user.timezone = "Europe/Moscow"
        setup.add(user)
        await setup.flush()
        for number in range(60):
            await NotificationService(setup).enqueue(
                user.id,
                NotificationType.HOMEWORK_GRADED,
                graded(number + 1),
                f"parallel-{number}",
                scheduled_for=DAY,
            )
        await setup.commit()

    first, second = SlowNotifier(), SlowNotifier()

    async def run(notifier: FakeNotifier) -> int:
        async with committed() as session:
            return (await dispatcher(session, notifier).dispatch_due(DAY)).sent

    sent_a, sent_b = await asyncio.gather(run(first), run(second))
    assert sent_a + sent_b == 60
    texts = [text for _, text in first.sent + second.sent]
    assert len(texts) == 60
    assert len(set(texts)) == 60  # у каждого уведомления свой assignment_id: дубль виден сразу
    assert sent_a > 0 and sent_b > 0  # оба действительно работали параллельно
    async with committed() as check:
        total = await check.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.dedup_key.like("parallel-%"),
                Notification.status == NotificationStatus.SENT,
                Notification.attempts == 1,
            )
        )
    assert total == 60
