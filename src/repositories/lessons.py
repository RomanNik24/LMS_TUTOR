"""Репозиторий уроков и участников (docs/04 §4)."""

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, exists, func, select
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

    async def remove_participants(self, lesson_id: int, student_ids: Sequence[int]) -> None:
        """Убрать участников из урока."""
        if not student_ids:
            return
        await self._session.execute(
            delete(LessonParticipant).where(
                LessonParticipant.lesson_id == lesson_id,
                LessonParticipant.student_id.in_(list(student_ids)),
            )
        )

    async def subject_codes(self, subject_ids: Sequence[int]) -> dict[int, str]:
        """Коды предметов по id одним запросом."""
        if not subject_ids:
            return {}
        stmt = select(Subject.id, Subject.code).where(Subject.id.in_(list(subject_ids)))
        return {row[0]: row[1] for row in (await self._session.execute(stmt)).all()}

    async def participants_for(
        self, lesson_ids: Sequence[int]
    ) -> dict[int, list[tuple[LessonParticipant, str]]]:
        """Участники с именами для нескольких уроков одним запросом."""
        if not lesson_ids:
            return {}
        stmt = (
            select(LessonParticipant, User.display_name)
            .join(User, User.id == LessonParticipant.student_id)
            .where(LessonParticipant.lesson_id.in_(list(lesson_ids)))
            .order_by(LessonParticipant.lesson_id, LessonParticipant.student_id)
        )
        grouped: dict[int, list[tuple[LessonParticipant, str]]] = {}
        for participant, name in (await self._session.execute(stmt)).all():
            grouped.setdefault(participant.lesson_id, []).append((participant, name))
        return grouped

    async def participant_counts(self, lesson_ids: Sequence[int]) -> dict[int, int]:
        """Число участников для нескольких уроков."""
        if not lesson_ids:
            return {}
        stmt = (
            select(LessonParticipant.lesson_id, func.count())
            .where(LessonParticipant.lesson_id.in_(list(lesson_ids)))
            .group_by(LessonParticipant.lesson_id)
        )
        return {row[0]: row[1] for row in (await self._session.execute(stmt)).all()}

    async def list_in_period(
        self,
        start: datetime,
        end: datetime,
        *,
        student_id: int | None,
        teacher_id: int | None,
        status: LessonStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Lesson], int]:
        """Уроки с началом в ``[start, end)`` по фильтрам; страница и общее число."""
        conditions = [Lesson.start_at >= start, Lesson.start_at < end]
        if teacher_id is not None:
            conditions.append(Lesson.teacher_id == teacher_id)
        if status is not None:
            conditions.append(Lesson.status == status)
        if student_id is not None:
            conditions.append(
                exists().where(
                    LessonParticipant.lesson_id == Lesson.id,
                    LessonParticipant.student_id == student_id,
                )
            )
        total = (
            await self._session.execute(select(func.count()).select_from(Lesson).where(*conditions))
        ).scalar_one()
        stmt = (
            select(Lesson)
            .where(*conditions)
            .order_by(Lesson.start_at, Lesson.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars()), total

    async def list_for_student(
        self, student_id: int, start: datetime, end: datetime
    ) -> list[Lesson]:
        """Уроки ученика с началом в ``[start, end)``."""
        stmt = (
            select(Lesson)
            .join(LessonParticipant, LessonParticipant.lesson_id == Lesson.id)
            .where(
                LessonParticipant.student_id == student_id,
                Lesson.start_at >= start,
                Lesson.start_at < end,
            )
            .order_by(Lesson.start_at, Lesson.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def get_for_student(self, lesson_id: int, student_id: int) -> Lesson | None:
        """Урок, только если ученик в нём участвует; иначе ``None`` (чужой урок = «нет»)."""
        stmt = (
            select(Lesson)
            .join(LessonParticipant, LessonParticipant.lesson_id == Lesson.id)
            .where(Lesson.id == lesson_id, LessonParticipant.student_id == student_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def next_starts_for_students(
        self, student_ids: Sequence[int], after: datetime
    ) -> dict[int, datetime]:
        """Начало ближайшего запланированного урока после ``after`` для каждого ученика.

        У учеников без такого урока ключа в ответе нет.
        """
        if not student_ids:
            return {}
        stmt = (
            select(LessonParticipant.student_id, func.min(Lesson.start_at))
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .where(
                LessonParticipant.student_id.in_(list(student_ids)),
                Lesson.status == LessonStatus.SCHEDULED,
                Lesson.start_at > after,
            )
            .group_by(LessonParticipant.student_id)
        )
        return {row[0]: row[1] for row in (await self._session.execute(stmt)).all()}
