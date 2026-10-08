"""Выборки для отчётов по ученику (docs/04 §11): ДЗ, срок сдачи, пробники, посещаемость."""

from datetime import date, datetime
from typing import cast

from sqlalchemy import func, select

from src.core.enums import AssignmentStatus, LessonStatus
from src.db.models import (
    ExamType,
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    MockExamResult,
)
from src.repositories.base import BaseRepository


class StatsRepository(BaseRepository[HomeworkAssignment]):
    """Агрегаты по одному ученику за период."""

    async def graded_rows(
        self, student_id: int, start: datetime, end: datetime
    ) -> list[tuple[datetime, int, int]]:
        """Проверенные работы периода: ``(graded_at, score, max_score)``, по времени проверки.

        ``expired`` без оценки сюда не попадают (docs/04 §11).
        """
        stmt = (
            select(HomeworkAssignment.graded_at, HomeworkAssignment.score, Homework.max_score)
            .join(Homework, Homework.id == HomeworkAssignment.homework_id)
            .where(
                HomeworkAssignment.student_id == student_id,
                HomeworkAssignment.status == AssignmentStatus.GRADED,
                HomeworkAssignment.graded_at.is_not(None),
                HomeworkAssignment.score.is_not(None),
                HomeworkAssignment.graded_at >= start,
                HomeworkAssignment.graded_at < end,
            )
            .order_by(HomeworkAssignment.graded_at, HomeworkAssignment.id)
        )
        # фильтр в запросе гарантирует непустые graded_at и score
        return [
            (cast(datetime, row[0]), cast(int, row[1]), row[2])
            for row in (await self._session.execute(stmt)).all()
        ]

    async def punctuality(self, student_id: int, start: datetime, end: datetime) -> tuple[int, int]:
        """``(в срок, всего)`` среди сданных, проверенных и сгоревших выдач периода.

        Период — по первоначальному сроку ``original_due_at``: пунктуальность относится к
        дедлайну. Сгоревшая выдача никогда не сдавалась вовремя.
        """
        on_time = HomeworkAssignment.submitted_at.is_not(None) & (
            HomeworkAssignment.submitted_at <= HomeworkAssignment.original_due_at
        )
        stmt = select(
            func.count().filter(on_time),
            func.count(),
        ).where(
            HomeworkAssignment.student_id == student_id,
            HomeworkAssignment.status.in_(
                [AssignmentStatus.SUBMITTED, AssignmentStatus.GRADED, AssignmentStatus.EXPIRED]
            ),
            HomeworkAssignment.original_due_at >= start,
            HomeworkAssignment.original_due_at < end,
        )
        row = (await self._session.execute(stmt)).one()
        return int(row[0]), int(row[1])

    async def mock_exams(
        self, student_id: int, first_day: date, last_day: date
    ) -> list[tuple[MockExamResult, ExamType]]:
        """Результаты пробников с ``first_day <= exam_date <= last_day``, по дате."""
        stmt = (
            select(MockExamResult, ExamType)
            .join(ExamType, ExamType.id == MockExamResult.exam_type_id)
            .where(
                MockExamResult.student_id == student_id,
                MockExamResult.exam_date >= first_day,
                MockExamResult.exam_date <= last_day,
            )
            .order_by(MockExamResult.exam_date, MockExamResult.id)
        )
        return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

    async def attendance(self, student_id: int, start: datetime, end: datetime) -> dict[str, int]:
        """Число отметок участия по статусам для уроков периода (отменённые уроки не считаются)."""
        stmt = (
            select(LessonParticipant.attendance, func.count())
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .where(
                LessonParticipant.student_id == student_id,
                Lesson.start_at >= start,
                Lesson.start_at < end,
                Lesson.status != LessonStatus.CANCELLED,
            )
            .group_by(LessonParticipant.attendance)
        )
        return {str(row[0].value): int(row[1]) for row in (await self._session.execute(stmt)).all()}
