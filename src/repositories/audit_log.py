"""Репозиторий журнала аудита (задача T1.06, docs/04 §7.2).

Журнал только пополняется: методов изменения и удаления нет.
"""

from sqlalchemy import func, select

from src.db.models import AuditLog, User
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

    async def page(
        self, *, limit: int, offset: int
    ) -> tuple[list[tuple[AuditLog, str | None]], int]:
        """Страница журнала: новые первыми, с именем автора; и общее число записей."""
        stmt = (
            select(AuditLog, User.display_name)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows: list[tuple[AuditLog, str | None]] = [
            (row[0], row[1]) for row in (await self._session.execute(stmt)).all()
        ]
        total = (
            await self._session.execute(select(func.count()).select_from(AuditLog))
        ).scalar_one()
        return rows, total
