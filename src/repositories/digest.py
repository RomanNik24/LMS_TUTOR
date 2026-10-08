"""Выборки для утренней сводки персоналу (T5.07, docs/05 §6.3). Только чтение."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, select

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
class DigestLesson:
    """Урок дня с именами участников."""

    start_at: datetime
    subject_code: str
    students: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DigestAssignment:
    """Выдача для строки сводки."""

    student_name: str
    title: str
    due_at: datetime


class DigestRepository(BaseRepository[Lesson]):
    """Запросы сводки."""

    async def lessons_between(self, start: datetime, end: datetime) -> list[DigestLesson]:
        """Не отменённые уроки с началом в ``[start, end)`` по времени начала."""
        stmt = (
            select(Lesson.id, Lesson.start_at, Subject.code)
            .join(Subject, Subject.id == Lesson.subject_id)
            .where(
                Lesson.start_at >= start,
                Lesson.start_at < end,
                Lesson.status != LessonStatus.CANCELLED,
            )
            .order_by(Lesson.start_at, Lesson.id)
        )
        lessons = (await self._session.execute(stmt)).all()
        if not lessons:
            return []
        names_stmt = (
            select(LessonParticipant.lesson_id, User.display_name)
            .join(User, User.id == LessonParticipant.student_id)
            .where(LessonParticipant.lesson_id.in_([row[0] for row in lessons]))
            .order_by(LessonParticipant.lesson_id, User.display_name)
        )
        names: dict[int, list[str]] = {}
        for lesson_id, name in (await self._session.execute(names_stmt)).all():
            names.setdefault(lesson_id, []).append(name)
        return [DigestLesson(row[1], row[2], tuple(names.get(row[0], ()))) for row in lessons]

    async def unsubmitted_for_lessons(
        self, start: datetime, end: datetime
    ) -> list[DigestAssignment]:
        """Активные выдачи учеников, у которых есть урок в ``[start, end)`` (по сроку)."""
        has_lesson = (
            select(LessonParticipant.student_id)
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .where(
                Lesson.start_at >= start,
                Lesson.start_at < end,
                Lesson.status == LessonStatus.SCHEDULED,
            )
        )
        return await self._assignments(
            HomeworkAssignment.status.in_(ACTIVE),
            HomeworkAssignment.student_id.in_(has_lesson),
        )

    async def deadlines_between(self, start: datetime, end: datetime) -> list[DigestAssignment]:
        """Активные выдачи со сроком в ``(start, end]``."""
        return await self._assignments(
            HomeworkAssignment.status.in_(ACTIVE),
            HomeworkAssignment.due_at > start,
            HomeworkAssignment.due_at <= end,
        )

    async def _assignments(self, *conditions: ColumnElement[bool]) -> list[DigestAssignment]:
        stmt = (
            select(User.display_name, Homework.title, HomeworkAssignment.due_at)
            .join(Homework, Homework.id == HomeworkAssignment.homework_id)
            .join(User, User.id == HomeworkAssignment.student_id)
            .where(*conditions, User.is_active.is_(True))
            .order_by(HomeworkAssignment.due_at, HomeworkAssignment.id)
        )
        return [DigestAssignment(*row) for row in (await self._session.execute(stmt)).all()]
