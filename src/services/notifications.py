"""``NotificationService``: постановка уведомлений в очередь (T5.03, docs/03 §8, docs/05 §6.4).

Правила:
- запись делается в ТОЙ ЖЕ транзакции, что и бизнес-изменение: сервис только добавляет строку
  и не делает commit, его делает вызывающий сервис вместе со своим изменением;
- ``dedup_key`` уникален: повторная постановка того же события ничего не создаёт;
- несрочное уведомление ставится «на сейчас», тихие часы применяет диспетчер перед отправкой;
- отмена и перенос урока срочные, если урок начинается меньше чем через 12 часов.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import URGENT_LESSON_CHANGE_HOURS
from src.core.enums import NotificationType
from src.core.timeutils import utcnow
from src.repositories.notifications import NotificationRepository


def is_urgent_lesson_change(now: datetime, *starts: datetime) -> bool:
    """Срочно ли изменение урока: любое из времён начала (старое, новое) ближе 12 часов."""
    horizon = now + timedelta(hours=URGENT_LESSON_CHANGE_HOURS)
    return any(start <= horizon for start in starts)


class NotificationService:
    """Очередь исходящих уведомлений."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД вызывающего сервиса (общая транзакция).
        """
        self._notifications = NotificationRepository(session)

    async def enqueue(
        self,
        user_id: int,
        type_: NotificationType,
        payload: Mapping[str, object],
        dedup_key: str,
        *,
        scheduled_for: datetime | None = None,
        is_urgent: bool = False,
    ) -> bool:
        """Поставить уведомление в очередь без commit.

        Args:
            user_id: Получатель.
            type_: Тип уведомления.
            payload: Данные для шаблона (контракт полей — в ``notification_render``).
            dedup_key: Ключ дедупликации (docs/05 §6.4).
            scheduled_for: Не раньше этого момента; по умолчанию — сейчас.
            is_urgent: Игнорировать тихие часы.

        Returns:
            ``True``, если запись создана; ``False``, если такой ``dedup_key`` уже был.
        """
        return await self._notifications.enqueue(
            user_id=user_id,
            type_=type_.value,
            payload=payload,
            dedup_key=dedup_key,
            scheduled_for=scheduled_for or utcnow(),
            is_urgent=is_urgent,
        )
