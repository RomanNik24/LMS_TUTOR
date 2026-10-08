"""Выборки для генераторов напоминаний (T5.05, docs/03 §9, docs/05 §6)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from src.core.constants import LESSON_MAX_MINUTES
from src.core.enums import AssignmentStatus, LessonStatus
from src.db.models import (
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    StudentProfile,
    Subject,
    User,
)
from src.repositories.base import BaseRepository

ACTIVE_ASSIGNMENT = (AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION)


@dataclass(frozen=True, slots=True)
class LessonReminderTarget:
    """Ученик, которому нужно напомнить об уроке."""

    lesson_id: int
    start_at: datetime
    student_id: int
    subject_code: str
    video_url: str | None
    board_url: str | None


@dataclass(frozen=True, slots=True)
class DeadlineTarget:
    """Выдача, по которой скоро истекает срок."""

    assignment_id: int
    student_id: int
    title: str
    due_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UnmarkedLesson:
    """Прошедший урок, который так и остался без отметки."""

    lesson_id: int
    teacher_id: int
    start_at: datetime
    subject_code: str


class ReminderRepository(BaseRepository[Lesson]):
    """Только чтение: кому и о чём напомнить."""

    async def lessons_starting(
        self, start_from: datetime, start_to: datetime
    ) -> list[LessonReminderTarget]:
        """Участники запланированных уроков с началом в ``[start_from, start_to]``.

        Ссылки: свои у урока, иначе из профиля ученика. Архивные ученики пропускаются.
        """
        stmt = (
            select(
                Lesson.id,
                Lesson.start_at,
                LessonParticipant.student_id,
                Subject.code,
                Lesson.video_url_override,
                Lesson.board_url_override,
                StudentProfile.video_url,
                StudentProfile.board_url,
            )
            .join(LessonParticipant, LessonParticipant.lesson_id == Lesson.id)
            .join(Subject, Subject.id == Lesson.subject_id)
            .join(User, User.id == LessonParticipant.student_id)
            .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
            .where(
                Lesson.status == LessonStatus.SCHEDULED,
                Lesson.start_at >= start_from,
                Lesson.start_at <= start_to,
                User.is_active.is_(True),
            )
            .order_by(Lesson.start_at, Lesson.id, LessonParticipant.student_id)
        )
        return [
            LessonReminderTarget(
                lesson_id=row[0],
                start_at=row[1],
                student_id=row[2],
                subject_code=row[3],
                video_url=row[4] or row[6],
                board_url=row[5] or row[7],
            )
            for row in (await self._session.execute(stmt)).all()
        ]

    async def deadlines_between(self, due_from: datetime, due_to: datetime) -> list[DeadlineTarget]:
        """Активные выдачи со сроком в ``[due_from, due_to]`` у неархивных учеников."""
        stmt = (
            select(
                HomeworkAssignment.id,
                HomeworkAssignment.student_id,
                Homework.title,
                HomeworkAssignment.due_at,
                HomeworkAssignment.created_at,
            )
            .join(Homework, Homework.id == HomeworkAssignment.homework_id)
            .join(User, User.id == HomeworkAssignment.student_id)
            .where(
                HomeworkAssignment.status.in_(ACTIVE_ASSIGNMENT),
                HomeworkAssignment.due_at >= due_from,
                HomeworkAssignment.due_at <= due_to,
                User.is_active.is_(True),
            )
            .order_by(HomeworkAssignment.due_at, HomeworkAssignment.id)
        )
        return [
            DeadlineTarget(row[0], row[1], row[2], row[3], row[4])
            for row in (await self._session.execute(stmt)).all()
        ]

    async def unmarked_lessons(self, end_from: datetime, end_to: datetime) -> list[UnmarkedLesson]:
        """Уроки в статусе ``scheduled`` с окончанием в ``[end_from, end_to]`` (ведёт активный)."""
        stmt = (
            select(Lesson.id, Lesson.teacher_id, Lesson.start_at, Subject.code)
            .join(Subject, Subject.id == Lesson.subject_id)
            .join(User, User.id == Lesson.teacher_id)
            .where(
                Lesson.status == LessonStatus.SCHEDULED,
                # нижняя граница по start_at: запрос использует индекс (status, start_at), issue #88
                Lesson.start_at >= end_from - timedelta(minutes=LESSON_MAX_MINUTES),
                Lesson.end_at >= end_from,
                Lesson.end_at <= end_to,
                User.is_active.is_(True),
            )
            .order_by(Lesson.end_at, Lesson.id)
        )
        return [
            UnmarkedLesson(row[0], row[1], row[2], row[3])
            for row in (await self._session.execute(stmt)).all()
        ]
