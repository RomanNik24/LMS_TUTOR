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

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.core.timeutils import local_date_of, to_local
from src.repositories.audit_log import AuditLogRepository
from src.repositories.finance import FinanceRepository, GroupSum
from src.repositories.stats import StatsRepository
from src.repositories.users import UserRepository
from src.schemas.finance import (
    AuditItem,
    AuditPage,
    CancellationStats,
    CancellationStudentRow,
    EarningsGroupBy,
    EarningsReport,
    EarningsRow,
)
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
CANCELLATION_TOP_STUDENTS = 20
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_TIME_GROUPS = (EarningsGroupBy.WEEK, EarningsGroupBy.MONTH)


def _safe_cell(value: str) -> str:
    """Защита от CSV-инъекции: ячейка, начинающаяся с символа формулы, получает апостроф."""
    return f"'{value}" if value.startswith(CSV_FORMULA_PREFIXES) else value


def _percent(part: float, whole: float) -> int:
    """Процент с округлением половины вверх (не банковским): 12,5 % → 13 %."""
    return int(part * PERCENT / whole + HALF)


class StatsService:
    """Отчёты по ученику."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис на сессию текущей единицы работы."""
        self._session = session
        self._stats = StatsRepository(session)
        self._users = UserRepository(session)
        self._finance = FinanceRepository(session)
        self._audit = AuditLogRepository(session)

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

    # ------------------------------------------------------------------ финансы (T7.02)

    async def earnings(
        self, actor: CurrentUser, start: datetime, end: datetime, group_by: EarningsGroupBy
    ) -> EarningsReport:
        """Заработано и ожидается за ``[start, end)`` с разрезом (docs/04 §11). Только владелец.

        Заработано — сумма ``price_snapshot`` оплачиваемых участий проведённых и отменённых уроков;
        ожидается — текущие цены учеников по участиям запланированных уроков.

        Raises:
            PermissionDeniedError: Не владелец.
            ValidationError: ``invalid_period``.
        """
        self._require_owner(actor)
        self._check_period(start, end)
        earned = await self._finance.earned_by(group_by, start, end, actor.timezone)
        expected = await self._finance.expected_by(group_by, start, end, actor.timezone)
        rows = self._merge(earned, expected, by_time=group_by in _TIME_GROUPS)
        return EarningsReport(
            period_start=start,
            period_end=end,
            group_by=group_by,
            timezone=actor.timezone,
            earned_total=sum(row.earned for row in rows),
            expected_total=sum(row.expected for row in rows),
            rows=rows,
        )

    async def cancellations(
        self, actor: CurrentUser, start: datetime, end: datetime
    ) -> CancellationStats:
        """Статистика отмен за период (персонал, без денег).

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: ``invalid_period``.
        """
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        self._check_period(start, end)
        lessons, participations = await self._finance.cancelled_counts(start, end)
        students = await self._finance.cancelled_by_student(
            start, end, limit=CANCELLATION_TOP_STUDENTS
        )
        return CancellationStats(
            period_start=start,
            period_end=end,
            cancelled_lessons=lessons,
            cancelled_participations=participations,
            by_student=[
                CancellationStudentRow(
                    student_id=row.student_id,
                    student_name=row.student_name,
                    cancelled_lessons=row.lessons,
                )
                for row in students
            ],
        )

    async def export_csv(self, actor: CurrentUser, start: datetime, end: datetime) -> str:
        """CSV оплаченных занятий за период: дата, ученик, предмет, сумма (только владелец).

        Лишних полей нет. Выгрузка пишется в журнал аудита. Значения, похожие на формулы
        (``=``, ``+``, ``-``, ``@``), экранируются апострофом.

        Raises:
            PermissionDeniedError: Не владелец.
            ValidationError: ``invalid_period``.
        """
        self._require_owner(actor)
        self._check_period(start, end)
        rows = await self._finance.export_rows(start, end)
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(texts.FINANCE_CSV_HEADER)
        for row in rows:
            writer.writerow(
                [
                    f"{to_local(row.start_at, actor.timezone):%Y-%m-%d}",
                    _safe_cell(row.student_name),
                    _safe_cell(texts.subject_name(row.subject_code)),
                    row.amount,
                ]
            )
        await self._audit.record(
            actor_user_id=actor.id,
            action="finance.exported",
            entity_type="finance",
            entity_id=None,
            data={"from": start.isoformat(), "to": end.isoformat(), "rows": len(rows)},
        )
        await self._session.commit()
        return buffer.getvalue()

    async def list_audit(
        self, actor: CurrentUser, *, limit: int = LIST_LIMIT_DEFAULT, offset: int = 0
    ) -> AuditPage:
        """Журнал аудита, новые записи первыми (только владелец).

        Raises:
            PermissionDeniedError: Не владелец.
            ValidationError: ``invalid_list_params``.
        """
        self._require_owner(actor)
        if not 1 <= limit <= LIST_LIMIT_MAX or offset < 0:
            raise ValidationError(texts.LIST_PARAMS_INVALID, code="invalid_list_params")
        rows, total = await self._audit.page(limit=limit, offset=offset)
        return AuditPage(
            items=[
                AuditItem(
                    id=entry.id,
                    actor_user_id=entry.actor_user_id,
                    actor_name=name,
                    action=entry.action,
                    entity_type=entry.entity_type,
                    entity_id=entry.entity_id,
                    data=entry.data,
                    created_at=entry.created_at,
                )
                for entry, name in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _require_owner(actor: CurrentUser) -> None:
        if actor.role != UserRole.OWNER:
            raise PermissionDeniedError()

    @staticmethod
    def _check_period(start: datetime, end: datetime) -> None:
        if end <= start or end - start > timedelta(days=PERIOD_MAX_DAYS):
            raise ValidationError(texts.LESSON_PERIOD_INVALID, code="invalid_period")

    @staticmethod
    def _merge(
        earned: list[GroupSum], expected: list[GroupSum], *, by_time: bool
    ) -> list[EarningsRow]:
        """Объединить «заработано» и «ожидается» по ключу группы."""
        rows: dict[str, EarningsRow] = {}
        for item in earned:
            rows[item.key] = EarningsRow(
                key=item.key,
                label=item.label,
                earned=item.amount,
                earned_lessons=item.lessons,
                expected=0,
                planned_lessons=0,
            )
        for item in expected:
            row = rows.get(item.key) or EarningsRow(
                key=item.key,
                label=item.label,
                earned=0,
                earned_lessons=0,
                expected=0,
                planned_lessons=0,
            )
            rows[item.key] = row.model_copy(
                update={"expected": item.amount, "planned_lessons": item.lessons}
            )
        ordered = list(rows.values())
        if by_time:
            return sorted(ordered, key=lambda row: row.key)
        return sorted(ordered, key=lambda row: (-(row.earned + row.expected), row.label))

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
