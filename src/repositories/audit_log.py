"""Репозиторий журнала аудита (задача T1.06, docs/04 §7.2).

Журнал только пополняется: методов изменения и удаления нет.
"""

from src.db.models import AuditLog
from src.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Доступ к таблице ``audit_log`` (только добавление записей)."""

    async def record(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | None,
        data: dict[str, object] | None = None,
    ) -> AuditLog:
        """Добавить запись о чувствительном действии.

        Args:
            actor_user_id: Кто выполнил действие (``None`` — система).
            action: Код действия, напр. ``invite.created``.
            entity_type: Тип сущности.
            entity_id: ID сущности.
            data: Данные «было/стало»; без персональных данных (docs/09 §4).

        Returns:
            Созданная запись журнала.
        """
        entry = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            data={} if data is None else data,
        )
        return await self.add(entry)
