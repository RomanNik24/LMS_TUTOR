"""События, порождающие уведомления (T5.06, docs/05 §6).

Сервисы вызывают эти методы в той же транзакции, что и бизнес-изменение (без ``commit``):
если изменение откатится, уведомление не появится, а если закоммитится, оно не потеряется.
Каждое событие имеет свой ``dedup_key``, поэтому повторное действие не создаёт дубль.
Поля ``payload`` — по контракту в ``notification_render``.

Ученику: ДЗ выдано, оценено, возвращено; урок отменён или перенесён.
Персоналу (все активные owner и manager): ДЗ сдано, ДЗ сгорело, ученик принял приглашение.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.enums import NotificationType
from src.core.timeutils import utcnow
from src.repositories.users import UserRepository
from src.services.notifications import NotificationService, is_urgent_lesson_change


def _epoch(moment: datetime) -> int:
    return int(moment.astimezone(UTC).timestamp())


class NotificationEvents:
    """Постановка уведомлений по доменным событиям."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать помощника.

        Args:
            session: Сессия БД вызывающего сервиса (общая транзакция).
        """
        self._queue = NotificationService(session)
        self._users = UserRepository(session)

    # ------------------------------------------------------------------ ученику

    async def homework_assigned(
        self, student_id: int, assignment_id: int, title: str, due_at: datetime
    ) -> None:
        """ДЗ выдано ученику."""
        await self._queue.enqueue(
            student_id,
            NotificationType.HOMEWORK_ASSIGNED,
            {"assignment_id": assignment_id, "title": title, "due_epoch": _epoch(due_at)},
            f"homework_assigned:{assignment_id}",
        )

    async def homework_graded(
        self, student_id: int, assignment_id: int, title: str, score: int, max_score: int
    ) -> None:
        """Работа оценена (повторная оценка с другим баллом уведомляет снова)."""
        await self._queue.enqueue(
            student_id,
            NotificationType.HOMEWORK_GRADED,
            {
                "assignment_id": assignment_id,
                "title": title,
                "score": score,
                "max_score": max_score,
            },
            f"homework_graded:{assignment_id}:{score}",
        )

    async def homework_returned(
        self,
        student_id: int,
        assignment_id: int,
        title: str,
        comment: str,
        submitted_at: datetime | None,
    ) -> None:
        """Работа возвращена на доработку (ключ привязан к сдаче, которую вернули)."""
        cycle = 0 if submitted_at is None else _epoch(submitted_at)
        await self._queue.enqueue(
            student_id,
            NotificationType.HOMEWORK_RETURNED,
            {"assignment_id": assignment_id, "title": title, "comment": comment},
            f"homework_returned:{assignment_id}:{cycle}",
        )

    async def lesson_cancelled(
        self,
        lesson_id: int,
        student_ids: list[int],
        subject_code: str,
        start_at: datetime,
        now: datetime | None = None,
    ) -> None:
        """Урок отменён; срочно, если он начинается меньше чем через 12 часов."""
        urgent = is_urgent_lesson_change(now or utcnow(), start_at)
        for student_id in student_ids:
            await self._queue.enqueue(
                student_id,
                NotificationType.LESSON_CANCELLED,
                {
                    "lesson_id": lesson_id,
                    "start_epoch": _epoch(start_at),
                    "subject": texts.subject_name(subject_code),
                },
                f"lesson_cancelled:{lesson_id}:{student_id}:{_epoch(start_at)}",
                is_urgent=urgent,
            )

    async def lesson_rescheduled(
        self,
        lesson_id: int,
        student_ids: list[int],
        subject_code: str,
        old_start: datetime,
        new_start: datetime,
        now: datetime | None = None,
    ) -> None:
        """Урок перенесён; срочно, если старое или новое время меньше чем через 12 часов."""
        urgent = is_urgent_lesson_change(now or utcnow(), old_start, new_start)
        for student_id in student_ids:
            await self._queue.enqueue(
                student_id,
                NotificationType.LESSON_RESCHEDULED,
                {
                    "lesson_id": lesson_id,
                    "old_start_epoch": _epoch(old_start),
                    "new_start_epoch": _epoch(new_start),
                    "subject": texts.subject_name(subject_code),
                },
                f"lesson_rescheduled:{lesson_id}:{student_id}:{_epoch(old_start)}:"
                f"{_epoch(new_start)}",
                is_urgent=urgent,
            )

    # ------------------------------------------------------------------ персоналу

    async def homework_submitted(
        self, assignment_id: int, title: str, student_name: str, submitted_at: datetime
    ) -> None:
        """Ученик сдал работу."""
        await self._to_staff(
            NotificationType.HOMEWORK_SUBMITTED,
            {"assignment_id": assignment_id, "title": title, "student_name": student_name},
            f"homework_submitted:{assignment_id}:{_epoch(submitted_at)}",
        )

    async def homework_expired(self, assignment_id: int, title: str, student_name: str) -> None:
        """Выдача сгорела."""
        await self._to_staff(
            NotificationType.HOMEWORK_EXPIRED,
            {"assignment_id": assignment_id, "title": title, "student_name": student_name},
            f"homework_expired:{assignment_id}",
        )

    async def student_joined(self, student_id: int, student_name: str) -> None:
        """Ученик принял приглашение."""
        await self._to_staff(
            NotificationType.STUDENT_JOINED,
            {"student_id": student_id, "student_name": student_name},
            f"student_joined:{student_id}",
        )

    async def _to_staff(
        self, kind: NotificationType, payload: dict[str, object], key_prefix: str
    ) -> None:
        for staff in await self._users.list_staff(include_archived=False):
            await self._queue.enqueue(staff.id, kind, payload, f"{key_prefix}:{staff.id}")
