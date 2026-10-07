"""Репозиторий очереди уведомлений (docs/04 §7.1, docs/03 §8)."""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.enums import NotificationStatus
from src.db.models import Notification
from src.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Доступ к таблице ``notifications``."""

    async def enqueue(
        self,
        *,
        user_id: int,
        type_: str,
        payload: Mapping[str, object],
        dedup_key: str,
        scheduled_for: datetime,
        is_urgent: bool,
    ) -> bool:
        """Поставить уведомление в очередь; ``False``, если запись с таким ``dedup_key`` уже есть.

        ``INSERT ... ON CONFLICT DO NOTHING`` не бросает ошибку и не откатывает транзакцию
        вызывающего: дубль просто игнорируется.
        """
        stmt = (
            pg_insert(Notification)
            .values(
                user_id=user_id,
                type=type_,
                payload=dict(payload),
                dedup_key=dedup_key,
                scheduled_for=scheduled_for,
                is_urgent=is_urgent,
            )
            .on_conflict_do_nothing(index_elements=["dedup_key"])
            .returning(Notification.id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def claim_due(self, now: datetime, limit: int) -> list[Notification]:
        """Забрать под блокировку готовые к отправке уведомления (``FOR UPDATE SKIP LOCKED``).

        Строки, которые уже держит другой диспетчер, пропускаются: два воркера не отправят
        одно и то же. Блокировка живёт до конца транзакции вызывающего.
        """
        stmt = (
            select(Notification)
            .where(
                Notification.status == NotificationStatus.PENDING,
                Notification.scheduled_for <= now,
            )
            .order_by(Notification.scheduled_for, Notification.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(stmt)).scalars())
