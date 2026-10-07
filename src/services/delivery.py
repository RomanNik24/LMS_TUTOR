"""``DeliveryService``: отправка одного уведомления и учёт результата (T5.02, docs/05 §6.4).

Правила:
- успех → ``sent`` и время отправки; если пользователь числился заблокировавшим бота, флаг
  снимается (раз сообщение дошло, бот разблокирован);
- бот заблокирован → у пользователя ``bot_blocked = true``, уведомление ``skipped``;
- временный сбой → попытка засчитывается; повторы через 1, 5, 15 минут (если транспорт просил
  подождать дольше — ждём дольше), после третьего повтора ``failed``;
- окончательный отказ → ``failed`` без повторов;
- сервис меняет только переданные объекты и не делает commit: транзакцией владеет диспетчер
  (T5.03), который берёт строки под ``FOR UPDATE SKIP LOCKED`` и фиксирует итог сам.
"""

import logging
from datetime import datetime, timedelta
from enum import StrEnum

from src.core.constants import NOTIFICATION_RETRY_DELAYS_SECONDS
from src.core.enums import NotificationStatus
from src.core.timeutils import utcnow
from src.db.models import Notification, User
from src.services.notifier import (
    Notifier,
    NotifierBlockedError,
    NotifierPermanentError,
    NotifierTemporaryError,
    OutgoingMessage,
)

logger = logging.getLogger(__name__)

ERROR_BLOCKED = "bot_blocked"
ERROR_NO_TELEGRAM = "no_telegram_id"


class DeliveryResult(StrEnum):
    """Итог попытки отправки."""

    SENT = "sent"
    SKIPPED = "skipped"
    RETRY = "retry"
    FAILED = "failed"


class DeliveryService:
    """Отправка уведомления и перевод его в нужный статус."""

    def __init__(self, notifier: Notifier) -> None:
        """Создать сервис.

        Args:
            notifier: Транспорт (Telegram или подмена в тестах).
        """
        self._notifier = notifier

    async def deliver(
        self,
        notification: Notification,
        user: User,
        message: OutgoingMessage,
        *,
        now: datetime | None = None,
    ) -> DeliveryResult:
        """Отправить сообщение получателю и записать результат в уведомление.

        Args:
            notification: Строка очереди (меняется на месте).
            user: Получатель (``bot_blocked`` может измениться).
            message: Готовое сообщение.
            now: Момент попытки (для тестов); по умолчанию — текущий.
        """
        moment = now or utcnow()
        if user.telegram_id is None:
            return self._finish(notification, NotificationStatus.SKIPPED, moment, ERROR_NO_TELEGRAM)
        try:
            await self._notifier.send(user.telegram_id, message)
        except NotifierBlockedError:
            user.bot_blocked = True
            user.updated_at = moment
            return self._finish(notification, NotificationStatus.SKIPPED, moment, ERROR_BLOCKED)
        except NotifierTemporaryError as error:
            return self._after_temporary_error(notification, error, moment)
        except NotifierPermanentError as error:
            return self._finish(notification, NotificationStatus.FAILED, moment, str(error))
        notification.attempts += 1
        notification.status = NotificationStatus.SENT
        notification.sent_at = moment
        notification.last_error = None
        notification.updated_at = moment
        if user.bot_blocked:
            user.bot_blocked = False
            user.updated_at = moment
        return DeliveryResult.SENT

    @staticmethod
    def _finish(
        notification: Notification, status: NotificationStatus, moment: datetime, reason: str
    ) -> DeliveryResult:
        notification.attempts += 1
        notification.status = status
        notification.last_error = reason
        notification.updated_at = moment
        if status == NotificationStatus.FAILED:
            logger.error(
                "Уведомление %s не отправлено: %s", notification.id, reason, exc_info=False
            )
            return DeliveryResult.FAILED
        return DeliveryResult.SKIPPED

    @staticmethod
    def _after_temporary_error(
        notification: Notification, error: NotifierTemporaryError, moment: datetime
    ) -> DeliveryResult:
        notification.attempts += 1
        notification.last_error = str(error)
        notification.updated_at = moment
        retries = len(NOTIFICATION_RETRY_DELAYS_SECONDS)
        if notification.attempts > retries:
            notification.status = NotificationStatus.FAILED
            logger.error(
                "Уведомление %s не отправлено после %s попыток: %s",
                notification.id,
                notification.attempts,
                error,
            )
            return DeliveryResult.FAILED
        delay = NOTIFICATION_RETRY_DELAYS_SECONDS[notification.attempts - 1]
        if error.retry_after is not None:
            delay = max(delay, error.retry_after)
        notification.scheduled_for = moment + timedelta(seconds=delay)
        return DeliveryResult.RETRY
