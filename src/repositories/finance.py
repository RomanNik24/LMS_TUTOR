"""Финансовые выборки (T7.01–T7.02, docs/04 §11). Только чтение; вызывать только для владельца."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Executable, SQLColumnExpression, String, cast, func, select

from src.core.enums import LessonStatus
from src.db.models import Lesson, LessonParticipant, StudentProfile, Subject, User
from src.repositories.base import BaseRepository
from src.schemas.finance import EarningsGroupBy

COUNTED_STATUSES = (LessonStatus.COMPLETED, LessonStatus.CANCELLED)


@dataclass(frozen=True, slots=True)
class GroupSum:
    """Сумма и число участий в одной группе разреза."""

    key: str
    label: str
    amount: int
    lessons: int


@dataclass(frozen=True, slots=True)
class ExportRow:
    """Оплаченное участие для выгрузки CSV: ровно нужные поля."""

    start_at: datetime
    student_name: str
    subject_code: str
    amount: int


@dataclass(frozen=True, slots=True)
class CancelledStudent:
    """Отмены ученика."""

    student_id: int
    student_name: str
    lessons: int


class FinanceRepository(BaseRepository[Lesson]):
    """Суммы «заработано» и «ожидается», разрезы, выгрузка и статистика отмен."""

    async def earned_between(self, start: datetime, end: datetime) -> int:
        """Сумма ``price_snapshot`` оплачиваемых участников уроков ``completed``/``cancelled``.

        Уроки с началом в ``[start, end)``; цена зафиксирована при отметке, поэтому смена цены
        ученика уже проведённые уроки не меняет.
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

    async def earned_by(
        self, group_by: EarningsGroupBy, start: datetime, end: datetime, tz_name: str
    ) -> list[GroupSum]:
        """Заработано по группам: те же правила, что у ``earned_between``."""
        key, label = self._group_columns(group_by, tz_name)
        amount = func.coalesce(func.sum(LessonParticipant.price_snapshot), 0)
        stmt = (
            select(key, label, amount, func.count())
            .select_from(LessonParticipant)
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .join(User, User.id == LessonParticipant.student_id)
            .join(Subject, Subject.id == Lesson.subject_id)
            .where(
                LessonParticipant.is_billable.is_(True),
                Lesson.status.in_(COUNTED_STATUSES),
                Lesson.start_at >= start,
                Lesson.start_at < end,
            )
            .group_by(key, label)
        )
        return [GroupSum(row[0], row[1], int(row[2]), row[3]) for row in await self._rows(stmt)]

    async def expected_by(
        self, group_by: EarningsGroupBy, start: datetime, end: datetime, tz_name: str
    ) -> list[GroupSum]:
        """Ожидается по группам: текущая цена профиля по участиям запланированных уроков."""
        key, label = self._group_columns(group_by, tz_name)
        amount = func.coalesce(func.sum(StudentProfile.lesson_price), 0)
        stmt = (
            select(key, label, amount, func.count())
            .select_from(LessonParticipant)
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .join(User, User.id == LessonParticipant.student_id)
            .join(Subject, Subject.id == Lesson.subject_id)
            .join(StudentProfile, StudentProfile.user_id == LessonParticipant.student_id)
            .where(
                Lesson.status == LessonStatus.SCHEDULED,
                Lesson.start_at >= start,
                Lesson.start_at < end,
            )
            .group_by(key, label)
        )
        return [GroupSum(row[0], row[1], int(row[2]), row[3]) for row in await self._rows(stmt)]

    async def export_rows(self, start: datetime, end: datetime) -> list[ExportRow]:
        """Оплачиваемые участия периода по времени начала урока (для CSV)."""
        stmt = (
            select(
                Lesson.start_at,
                User.display_name,
                Subject.code,
                func.coalesce(LessonParticipant.price_snapshot, 0),
            )
            .select_from(LessonParticipant)
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .join(User, User.id == LessonParticipant.student_id)
            .join(Subject, Subject.id == Lesson.subject_id)
            .where(
                LessonParticipant.is_billable.is_(True),
                Lesson.status.in_(COUNTED_STATUSES),
                Lesson.start_at >= start,
                Lesson.start_at < end,
            )
            .order_by(Lesson.start_at, Lesson.id, User.display_name)
        )
        return [ExportRow(*row) for row in await self._rows(stmt)]

    async def cancelled_counts(self, start: datetime, end: datetime) -> tuple[int, int]:
        """Число отменённых уроков и участий в них с началом в ``[start, end)``."""
        conditions = [
            Lesson.status == LessonStatus.CANCELLED,
            Lesson.start_at >= start,
            Lesson.start_at < end,
        ]
        lessons = (
            await self._session.execute(select(func.count()).select_from(Lesson).where(*conditions))
        ).scalar_one()
        participations = (
            await self._session.execute(
                select(func.count())
                .select_from(LessonParticipant)
                .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
                .where(*conditions)
            )
        ).scalar_one()
        return lessons, participations

    async def cancelled_by_student(
        self, start: datetime, end: datetime, *, limit: int
    ) -> list[CancelledStudent]:
        """Ученики с наибольшим числом отменённых занятий."""
        count = func.count()
        stmt = (
            select(User.id, User.display_name, count)
            .select_from(LessonParticipant)
            .join(Lesson, Lesson.id == LessonParticipant.lesson_id)
            .join(User, User.id == LessonParticipant.student_id)
            .where(
                Lesson.status == LessonStatus.CANCELLED,
                Lesson.start_at >= start,
                Lesson.start_at < end,
            )
            .group_by(User.id, User.display_name)
            .order_by(count.desc(), User.display_name)
            .limit(limit)
        )
        return [CancelledStudent(*row) for row in await self._rows(stmt)]

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _group_columns(
        group_by: EarningsGroupBy, tz_name: str
    ) -> tuple[SQLColumnExpression[str], SQLColumnExpression[str]]:
        if group_by == EarningsGroupBy.STUDENT:
            return cast(LessonParticipant.student_id, String), User.display_name
        if group_by == EarningsGroupBy.SUBJECT:
            return Subject.code, Subject.name
        unit = "week" if group_by == EarningsGroupBy.WEEK else "month"
        local_start = func.date_trunc(unit, func.timezone(tz_name, Lesson.start_at))
        day = func.to_char(local_start, "YYYY-MM-DD")
        return day, day

    async def _rows(self, stmt: Executable) -> list[tuple[Any, ...]]:
        return [tuple(row) for row in (await self._session.execute(stmt)).all()]
