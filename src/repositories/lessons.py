"""Репозиторий уроков и участников (docs/04 §4)."""

from collections.abc import Sequence

from sqlalchemy import select

from src.db.models import Lesson, LessonParticipant, Subject, User
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

    async def get_by_id(self, lesson_id: int, *, for_update: bool = False) -> Lesson | None:
        """Урок по id; ``for_update`` блокирует строку на время транзакции."""
        stmt = select(Lesson).where(Lesson.id == lesson_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def participants(self, lesson_id: int) -> list[LessonParticipant]:
        """Участники урока по возрастанию ``student_id``."""
        stmt = (
            select(LessonParticipant)
            .where(LessonParticipant.lesson_id == lesson_id)
            .order_by(LessonParticipant.student_id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def participants_with_names(self, lesson_id: int) -> list[tuple[LessonParticipant, str]]:
        """Участники урока вместе с именами для ответа сотрудникам."""
        stmt = (
            select(LessonParticipant, User.display_name)
            .join(User, User.id == LessonParticipant.student_id)
            .where(LessonParticipant.lesson_id == lesson_id)
            .order_by(LessonParticipant.student_id)
        )
        return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

    async def subject_code(self, subject_id: int) -> str:
        """Код предмета по id."""
        stmt = select(Subject.code).where(Subject.id == subject_id)
        return (await self._session.execute(stmt)).scalar_one()
