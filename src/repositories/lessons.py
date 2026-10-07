"""Репозиторий уроков и участников (docs/04 §4)."""

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.enums import LessonStatus
from src.core.timeutils import local_date_of
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

    async def insert_generated(
        self, rows: Sequence[dict[str, object]]
    ) -> list[tuple[int, datetime]]:
        """Вставить уроки из шаблона; конфликты (дубль или пересечение) молча пропускаются.

        ``ON CONFLICT DO NOTHING`` без цели покрывает и ``UNIQUE (template_id, start_at)``,
        и ``EXCLUDE``: повторный запуск не создаёт дублей и не падает на занятом времени.

        Returns:
            ``(id, start_at)`` только реально созданных уроков.
        """
        if not rows:
            return []
        stmt = (
            pg_insert(Lesson)
            .values(list(rows))
            .on_conflict_do_nothing()
            .returning(Lesson.id, Lesson.start_at)
        )
        return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

    async def delete_future_generated(self, template_id: int, now: datetime) -> int:
        """Удалить будущие неизменённые запланированные уроки шаблона; вернуть их число."""
        stmt = (
            delete(Lesson)
            .where(
                Lesson.template_id == template_id,
                Lesson.start_at > now,
                Lesson.is_detached.is_(False),
                Lesson.status == LessonStatus.SCHEDULED,
            )
            .returning(Lesson.id)
        )
        return len((await self._session.execute(stmt)).all())

    async def local_dates_of_template(self, template_id: int, tz_name: str) -> set[date]:
        """Местные даты всех уроков шаблона (любых статусов): их не пересоздаём при правке."""
        stmt = select(Lesson.start_at).where(Lesson.template_id == template_id)
        return {
            local_date_of(row, tz_name) for row in (await self._session.execute(stmt)).scalars()
        }

    async def add_participants_bulk(self, pairs: Sequence[tuple[int, int]]) -> None:
        """Добавить участников пачкой: ``(lesson_id, student_id)``."""
        self._session.add_all(
            [LessonParticipant(lesson_id=lid, student_id=sid) for lid, sid in pairs]
        )
        await self._session.flush()
