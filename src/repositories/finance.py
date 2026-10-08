"""Финансовые выборки (T7.01–T7.02, docs/04 §11). Только чтение; вызывать только для владельца."""

from datetime import datetime

from sqlalchemy import func, select

from src.core.enums import LessonStatus
from src.db.models import Lesson, LessonParticipant, StudentProfile
from src.repositories.base import BaseRepository

COUNTED_STATUSES = (LessonStatus.COMPLETED, LessonStatus.CANCELLED)


class FinanceRepository(BaseRepository[Lesson]):
    """Суммы «заработано» и «ожидается»."""

    async def earned_between(self, start: datetime, end: datetime) -> int:
        """Сумма ``price_snapshot`` оплачиваемых участников уроков ``completed``/``cancelled``.

        Уроки с началом в ``[start, end)``; цена зафиксирована при отметке, поэтому
        смена цены ученика уже проведённые уроки не меняет.
        """
        stmt = (
            select(func.coalesce(func.sum(LessonParticipant.price_snapshot), 0))
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .where(
                LessonParticipant.is_billable.is_(True),
                Lesson.status.in_(COUNTED_STATUSES),
                Lesson.start_at >= start,
                Lesson.start_at < end,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one() or 0)

    async def expected_between(self, start: datetime, end: datetime) -> int:
        """Сумма текущих цен учеников по участникам запланированных уроков ``[start, end)``."""
        stmt = (
            select(func.coalesce(func.sum(StudentProfile.lesson_price), 0))
            .select_from(LessonParticipant)
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .join(StudentProfile, StudentProfile.user_id == LessonParticipant.student_id)
            .where(
                Lesson.status == LessonStatus.SCHEDULED,
                Lesson.start_at >= start,
                Lesson.start_at < end,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one() or 0)
