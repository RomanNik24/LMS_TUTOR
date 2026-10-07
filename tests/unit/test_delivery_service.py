"""DeliveryService: статусы уведомления по итогам отправки (T5.02, docs/05 §6.4)."""

from datetime import UTC, datetime, timedelta

from src.core.constants import NOTIFICATION_RETRY_DELAYS_SECONDS
from src.core.enums import NotificationStatus, UserRole
from src.db.models import Notification, User
from src.services.delivery import DeliveryResult, DeliveryService
from src.services.notifier import (
    NotifierBlockedError,
    NotifierPermanentError,
    NotifierTemporaryError,
    OutgoingMessage,
)

NOW = datetime(2030, 10, 14, 12, 0, tzinfo=UTC)
MESSAGE = OutgoingMessage(text="Привет")


class FakeNotifier:
    """Подмена транспорта: бросает заданные ошибки по очереди, иначе успешно отправляет."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.sent: list[int] = []

    async def send(self, telegram_id: int, message: OutgoingMessage) -> None:
        del message
        if self.errors:
            raise self.errors.pop(0)
        self.sent.append(telegram_id)


def make_user(**extra: object) -> User:
    return User(role=UserRole.STUDENT, display_name="Аня", telegram_id=555, **extra)


def make_notification() -> Notification:
    return Notification(
        id=1,
        user_id=1,
        type="homework_graded",
        payload={},
        dedup_key="k",
        scheduled_for=NOW,
        status=NotificationStatus.PENDING,
        attempts=0,
    )


async def test_success_marks_sent() -> None:
    notifier = FakeNotifier()
    row = make_notification()
    result = await DeliveryService(notifier).deliver(row, make_user(), MESSAGE, now=NOW)
    assert result == DeliveryResult.SENT
    assert (row.status, row.attempts, row.sent_at, row.last_error) == (
        NotificationStatus.SENT,
        1,
        NOW,
        None,
    )
    assert notifier.sent == [555]


async def test_success_clears_bot_blocked_flag() -> None:
    user = make_user(bot_blocked=True)
    await DeliveryService(FakeNotifier()).deliver(make_notification(), user, MESSAGE, now=NOW)
    assert user.bot_blocked is False


async def test_blocked_bot_marks_user_and_skips() -> None:
    user = make_user(bot_blocked=False)
    row = make_notification()
    notifier = FakeNotifier(NotifierBlockedError("blocked"))
    result = await DeliveryService(notifier).deliver(row, user, MESSAGE, now=NOW)
    assert result == DeliveryResult.SKIPPED
    assert user.bot_blocked is True
    assert row.status == NotificationStatus.SKIPPED
    assert row.last_error == "bot_blocked"
    assert row.sent_at is None


async def test_user_without_telegram_is_skipped_without_sending() -> None:
    user = User(role=UserRole.STUDENT, display_name="Аня", telegram_id=None)
    notifier = FakeNotifier()
    row = make_notification()
    result = await DeliveryService(notifier).deliver(row, user, MESSAGE, now=NOW)
    assert result == DeliveryResult.SKIPPED
    assert notifier.sent == []
    assert row.status == NotificationStatus.SKIPPED


async def test_permanent_error_fails_without_retry() -> None:
    row = make_notification()
    notifier = FakeNotifier(NotifierPermanentError("chat not found"))
    result = await DeliveryService(notifier).deliver(row, make_user(), MESSAGE, now=NOW)
    assert result == DeliveryResult.FAILED
    assert row.status == NotificationStatus.FAILED
    assert row.last_error == "chat not found"


async def test_temporary_errors_retry_after_1_5_15_minutes_then_fail() -> None:
    errors = [NotifierTemporaryError("network") for _ in range(4)]
    notifier = FakeNotifier(*errors)
    service = DeliveryService(notifier)
    row = make_notification()
    user = make_user()
    moment = NOW
    for delay in NOTIFICATION_RETRY_DELAYS_SECONDS:
        result = await service.deliver(row, user, MESSAGE, now=moment)
        assert result == DeliveryResult.RETRY
        assert row.status == NotificationStatus.PENDING
        assert row.scheduled_for == moment + timedelta(seconds=delay)
        moment = row.scheduled_for
    assert NOTIFICATION_RETRY_DELAYS_SECONDS == (60, 300, 900)
    result = await service.deliver(row, user, MESSAGE, now=moment)
    assert result == DeliveryResult.FAILED
    assert row.status == NotificationStatus.FAILED
    assert row.attempts == 4


async def test_retry_after_longer_than_schedule_wins() -> None:
    row = make_notification()
    notifier = FakeNotifier(NotifierTemporaryError("flood", retry_after=600))
    await DeliveryService(notifier).deliver(row, make_user(), MESSAGE, now=NOW)
    assert row.scheduled_for == NOW + timedelta(seconds=600)


async def test_success_after_retry_marks_sent() -> None:
    notifier = FakeNotifier(NotifierTemporaryError("network"))
    service = DeliveryService(notifier)
    row = make_notification()
    user = make_user()
    assert await service.deliver(row, user, MESSAGE, now=NOW) == DeliveryResult.RETRY
    later = row.scheduled_for
    assert await service.deliver(row, user, MESSAGE, now=later) == DeliveryResult.SENT
    assert (row.status, row.attempts, row.last_error) == (NotificationStatus.SENT, 2, None)
