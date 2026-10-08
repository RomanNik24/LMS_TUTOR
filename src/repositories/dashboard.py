"""Именованные выборки дашборда «Сегодня» (T7.01, docs/01 §4.3). Только чтение.

Число SQL-запросов не зависит от числа учеников: имена участников берутся одним запросом на блок
через ``IN``, счётчики — отдельными агрегатами.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, exists, func, select

from src.core.constants import LESSON_MAX_MINUTES
from src.core.enums import AssignmentStatus, LessonStatus
from src.db.models import (
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    Subject,
    User,
)
from src.repositories.base import BaseRepository

ACTIVE = (AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION)


@dataclass(frozen=True, slots=True)
class LessonRow:
    """Урок блока дашборда."""

    id: int
    subject_code: str
    start_at: datetime
    end_at: datetime
    status: LessonStatus


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """Работа в очереди проверки."""

    assignment_id: int
    student_name: str
    title: str
    submitted_at: datetime | None


@dataclass(frozen=True, slots=True)
class AssignmentRow:
    """Активная выдача блока дашборда."""

    assignment_id: int
    student_id: int
    student_name: str
    title: str
    status: AssignmentStatus
    due_at: datetime


class DashboardRepository(BaseRepository[Lesson]):
    """Запросы пяти блоков дашборда."""

    async def lessons_between(
        self, start: datetime, end: datetime, *, limit: int
    ) -> tuple[list[LessonRow], int]:
        """Уроки с началом в ``[start, end)``, в том числе отменённые (видны со статусом)."""
        conditions = [Lesson.start_at >= start, Lesson.start_at < end]
        return await self._lessons(conditions, limit=limit, newest_first=False)

    async def unmarked_lessons(
        self, since: datetime, now: datetime, *, limit: int
    ) -> tuple[list[LessonRow], int]:
        """Уроки ``scheduled``, закончившиеся в ``[since, now]``: самые свежие первыми."""
        conditions = [
            Lesson.status == LessonStatus.SCHEDULED,
            # Нижняя граница по start_at (урок не длиннее LESSON_MAX_MINUTES) позволяет использовать
            # индекс (status, start_at): иначе читались бы все запланированные уроки (issue #88).
            Lesson.start_at >= since - timedelta(minutes=LESSON_MAX_MINUTES),
            Lesson.end_at >= since,
            Lesson.end_at <= now,
        ]
        return await self._lessons(conditions, limit=limit, newest_first=True)

    async def student_names(self, lesson_ids: Sequence[int]) -> dict[int, list[str]]:
        """Имена участников уроков одним запросом."""
        if not lesson_ids:
            return {}
        stmt = (
            select(LessonParticipant.lesson_id, User.display_name)
            .join(User, User.id == LessonParticipant.student_id)
            .where(LessonParticipant.lesson_id.in_(lesson_ids))
            .order_by(LessonParticipant.lesson_id, User.display_name)
        )
        names: dict[int, list[str]] = {}
        for lesson_id, name in (await self._session.execute(stmt)).all():
            names.setdefault(lesson_id, []).append(name)
        return names

    async def review_queue(self, *, limit: int) -> tuple[list[ReviewRow], int]:
        """Сданные работы: самые давние первыми и общее число."""
        condition = HomeworkAssignment.status == AssignmentStatus.SUBMITTED
        stmt = (
            select(
                HomeworkAssignment.id,
                User.display_name,
                Homework.title,
                HomeworkAssignment.submitted_at,
            )
            .join(Homework, Homework.id == HomeworkAssignment.homework_id)
            .join(User, User.id == HomeworkAssignment.student_id)
            .where(condition)
            .order_by(HomeworkAssignment.submitted_at, HomeworkAssignment.id)
            .limit(limit)
        )
        rows = [ReviewRow(*row) for row in (await self._session.execute(stmt)).all()]
        total = await self._count(HomeworkAssignment, condition)
        return rows, total

    async def unsubmitted_for_lessons(
        self, start: datetime, end: datetime, *, limit: int
    ) -> tuple[list[AssignmentRow], int]:
        """Активные выдачи, срок которых не позже урока ученика в ``[start, end)``.

        Урок должен быть запланированным; ``due_at <= Lesson.start_at`` — ученик должен был сдать
        работу к этому занятию (docs/01 §4.3).
        """
        has_lesson = exists().where(
            LessonParticipant.student_id == HomeworkAssignment.student_id,
            Lesson.id == LessonParticipant.lesson_id,
            Lesson.status == LessonStatus.SCHEDULED,
            Lesson.start_at >= start,
            Lesson.start_at < end,
            HomeworkAssignment.due_at <= Lesson.start_at,
        )
        return await self._active_assignments([has_lesson], limit=limit)

    async def deadlines_between(
        self, start: datetime, end: datetime, *, limit: int
    ) -> tuple[list[AssignmentRow], int]:
        """Активные выдачи со сроком в ``(start, end]``."""
        return await self._active_assignments(
            [HomeworkAssignment.due_at > start, HomeworkAssignment.due_at <= end], limit=limit
        )

    # ------------------------------------------------------------------ внутреннее

    async def _lessons(
        self, conditions: list[ColumnElement[bool]], *, limit: int, newest_first: bool
    ) -> tuple[list[LessonRow], int]:
        order = (
            (Lesson.start_at.desc(), Lesson.id) if newest_first else (Lesson.start_at, Lesson.id)
        )
        stmt = (
            select(Lesson.id, Subject.code, Lesson.start_at, Lesson.end_at, Lesson.status)
            .join(Subject, Subject.id == Lesson.subject_id)
            .where(*conditions)
            .order_by(*order)
            .limit(limit)
        )
        rows = [LessonRow(*row) for row in (await self._session.execute(stmt)).all()]
        return rows, await self._count(Lesson, *conditions)

    async def _active_assignments(
        self, extra: list[ColumnElement[bool]], *, limit: int
    ) -> tuple[list[AssignmentRow], int]:
        conditions = [HomeworkAssignment.status.in_(ACTIVE), User.is_active.is_(True), *extra]
        stmt = (
            select(
                HomeworkAssignment.id,
                HomeworkAssignment.student_id,
                User.display_name,
                Homework.title,
                HomeworkAssignment.status,
                HomeworkAssignment.due_at,
            )
            .join(Homework, Homework.id == HomeworkAssignment.homework_id)
            .join(User, User.id == HomeworkAssignment.student_id)
            .where(*conditions)
            .order_by(HomeworkAssignment.due_at, HomeworkAssignment.id)
            .limit(limit)
        )
        rows = [AssignmentRow(*row) for row in (await self._session.execute(stmt)).all()]
        count_stmt = (
            select(func.count())
            .select_from(HomeworkAssignment)
            .join(User, User.id == HomeworkAssignment.student_id)
            .where(*conditions)
        )
        return rows, (await self._session.execute(count_stmt)).scalar_one()

    async def _count(
        self, model: type[Lesson] | type[HomeworkAssignment], *conditions: ColumnElement[bool]
    ) -> int:
        stmt = select(func.count()).select_from(model).where(*conditions)
        return (await self._session.execute(stmt)).scalar_one()
