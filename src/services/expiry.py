"""``ExpiryService``: истечение просроченных выдач (T4.10, docs/04 §5.4).

Правило: ``now > due_at`` И переносы исчерпаны (``extensions_count = 2``) И статус ``assigned``
или ``needs_revision`` → ``expired`` с ``expired_at``. Если переносов осталось меньше двух, срок
вышел, но выдача остаётся «просроченной» (вычисляется на лету), и преподаватель решает, переносить
ли её.

Операция идемпотентна: повторный запуск ничего не меняет. Telegram здесь не вызывается:
уведомления об истечении подключаются на этапе 5. Метод рассчитан на воркер (запуск по расписанию
каждые 5 минут, этап 7) и не требует пользователя.
"""

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.timeutils import utcnow
from src.db.models.homework import MAX_EXTENSIONS
from src.repositories.audit_log import AuditLogRepository
from src.repositories.homework import HomeworkAssignmentRepository

AUDIT_EXPIRED = "assignment.expired"
AUDIT_ENTITY_ASSIGNMENT = "homework_assignment"


class ExpiryResult(BaseModel):
    """Итог запуска: сколько выдач истекло и какие."""

    expired: int
    assignment_ids: list[int]


class ExpiryService:
    """Автоматическое истечение выдач после исчерпания переносов."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._assignments = HomeworkAssignmentRepository(session)
        self._audit = AuditLogRepository(session)

    async def expire_due_assignments(self, now: datetime | None = None) -> ExpiryResult:
        """Перевести просроченные выдачи в ``expired``.

        Args:
            now: Момент проверки; по умолчанию — текущее время (параметр нужен тестам и воркеру).

        Returns:
            Количество и id истёкших выдач (пусто, если делать было нечего).
        """
        moment = utcnow() if now is None else now
        ids = await self._assignments.expire_due(moment, MAX_EXTENSIONS)
        for assignment_id in ids:
            await self._audit.record(
                actor_user_id=None,
                action=AUDIT_EXPIRED,
                entity_type=AUDIT_ENTITY_ASSIGNMENT,
                entity_id=assignment_id,
                data={},
            )
        await self._session.commit()
        return ExpiryResult(expired=len(ids), assignment_ids=ids)
