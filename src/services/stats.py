"""``StatsService``: отчёты по ученику (docs/04 §11, docs/08 §4 и §5.2, T6.04).

Формулы (docs/04 §11):
- средний процент ДЗ по неделям — среднее ``score * 100 / max_score`` проверенных работ,
  сгруппированных по ISO-неделе ``graded_at`` в часовом поясе ученика; ``expired`` без оценки
  не входит;
- «% в срок» — ``count(on_time) / count(submitted | graded | expired)`` среди выдач периода;
- пробники — серия результатов: оценка/тестовый балл или процент от максимума.

Ученик видит только свой отчёт; персонал — отчёт любого ученика. Финансов в отчёте нет.
Сервис только читает: ``commit`` не нужен.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.core.timeutils import local_date_of
from src.repositories.stats import StatsRepository
from src.repositories.users import UserRepository
from src.schemas.reports import (
    AttendanceStats,
    MockExamPoint,
    OnTimeStats,
    StudentReport,
    WeeklyHomeworkPoint,
)
from src.schemas.schedule import PERIOD_MAX_DAYS
from src.services.auth import STAFF_ROLES

PERCENT = 100
HALF = 0.5


def _percent(part: float, whole: float) -> int:
    """Процент с округлением половины вверх (не банковским): 12,5 % → 13 %."""
    return int(part * PERCENT / whole + HALF)


class StatsService:
    """Отчёты по ученику."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис на сессию текущей единицы работы."""
        self._stats = StatsRepository(session)
        self._users = UserRepository(session)

    async def my_report(self, actor: CurrentUser, start: datetime, end: datetime) -> StudentReport:
        """Собственный отчёт ученика за ``[start, end)``.

        Raises:
            PermissionDeniedError: Не ученик.
            ValidationError: ``invalid_period``.
        """
        if actor.role != UserRole.STUDENT:
            raise PermissionDeniedError()
        return await self._report(actor.id, actor.timezone, start, end)

    async def student_report(
        self, actor: CurrentUser, student_id: int, start: datetime, end: datetime
    ) -> StudentReport:
        """Отчёт ученика для персонала.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``student_not_found``.
            ValidationError: ``invalid_period``.
        """
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        student = await self._users.get_by_id(student_id)
        if student is None or student.role != UserRole.STUDENT:
            raise NotFoundError(texts.STUDENT_NOT_FOUND, code="student_not_found")
        return await self._report(student.id, student.timezone, start, end)

    # ------------------------------------------------------------------ внутреннее

    async def _report(
        self, student_id: int, timezone: str, start: datetime, end: datetime
    ) -> StudentReport:
        if end <= start or end - start > timedelta(days=PERIOD_MAX_DAYS):
            raise ValidationError(texts.LESSON_PERIOD_INVALID, code="invalid_period")
        graded = await self._stats.graded_rows(student_id, start, end)
        on_time, total = await self._stats.punctuality(student_id, start, end)
        first_day = local_date_of(start, timezone)
        last_day = local_date_of(end - timedelta(microseconds=1), timezone)
        exams = await self._stats.mock_exams(student_id, first_day, last_day)
        attendance = await self._stats.attendance(student_id, start, end)
        return StudentReport(
            student_id=student_id,
            timezone=timezone,
            homework_weekly=self._weekly(graded, timezone),
            homework_last_percent=(_percent(graded[-1][1], graded[-1][2]) if graded else None),
            on_time=OnTimeStats(
                on_time_count=on_time,
                total_count=total,
                percent=_percent(on_time, total) if total else None,
            ),
            mock_exams=[
                MockExamPoint(
                    exam_date=result.exam_date,
                    exam_type_code=exam_type.code,
                    exam_type_name=exam_type.name,
                    result_kind=exam_type.result_kind,
                    primary_score=result.primary_score,
                    max_primary=result.max_primary,
                    converted_value=result.converted_value,
                    scale_applicable=result.converted_value is not None,
                    percent=_percent(result.primary_score, result.max_primary),
                )
                for result, exam_type in exams
            ],
            attendance=AttendanceStats(
                attended=attendance.get("attended", 0),
                no_show=attendance.get("no_show", 0),
                cancelled=attendance.get("cancelled", 0),
                pending=attendance.get("pending", 0),
            ),
        )

    @staticmethod
    def _weekly(
        graded: list[tuple[datetime, int, int]], timezone: str
    ) -> list[WeeklyHomeworkPoint]:
        """Среднее по проверенным работам каждой ISO-недели (неделя — по поясу ученика)."""
        weeks: dict[date, list[float]] = defaultdict(list)
        for graded_at, score, max_score in graded:
            day = local_date_of(graded_at, timezone)
            monday = day - timedelta(days=day.weekday())
            weeks[monday].append(score * PERCENT / max_score)
        return [
            WeeklyHomeworkPoint(
                week_start=monday,
                average_percent=int(sum(values) / len(values) + HALF),
                graded_count=len(values),
            )
            for monday, values in sorted(weeks.items())
        ]
