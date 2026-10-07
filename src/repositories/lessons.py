"""Репозиторий уроков и участников (docs/04 §4)."""

from collections.abc import Sequence

from sqlalchemy import select

from src.db.models import Lesson, LessonParticipant
from src.repositories.base import BaseRepository


class LessonRepository(BaseRepository[Lesson]):
    """Доступ к таблицам ``lessons`` и ``lesson_participants``."""

    async def add_participants(self, lesson_id: int, student_ids: Sequence[int]) -> None:
        """Добавить участников урока (посещаемость ``pending``, цена не зафиксирована)."""
        self._session.add_all(
            [LessonParticipant(lesson_id=lesson_id, student_id=sid) for sid in student_ids]
        )
        await self._session.flush()

    async def participant_ids(self, lesson_id: int) -> list[int]:
        """``student_id`` участников урока по возрастанию."""
        stmt = (
            select(LessonParticipant.student_id)
            .where(LessonParticipant.lesson_id == lesson_id)
            .order_by(LessonParticipant.student_id)
        )
        return list((await self._session.execute(stmt)).scalars())
