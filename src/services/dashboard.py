"""``DashboardService``: дашборд «Сегодня» (T7.01, docs/01 §4.3, docs/08 §5.1).

Пять блоков для всего персонала; владелец дополнительно получает заработок текущего месяца.
Менеджер получает другую схему без финансовых полей, а финансовый репозиторий для него даже не
вызывается. «Сегодня» и «месяц» считаются в часовом поясе сотрудника. Сервис только читает.
"""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    DASHBOARD_DEADLINE_HOURS,
    DASHBOARD_LESSONS_MAX,
    DASHBOARD_TOP_ITEMS,
    UNMARKED_LESSON_LOOKBACK_DAYS,
)
from src.core.current_user import CurrentUser
from src.core.enums import LessonStatus, UserRole
from src.core.exceptions import PermissionDeniedError
from src.core.timeutils import day_bounds_utc, local_date_of, month_bounds_utc, utcnow
from src.repositories.dashboard import AssignmentRow, DashboardRepository
from src.repositories.finance import FinanceRepository
from src.schemas.dashboard import (
    DashboardAssignmentItem,
    DashboardAssignmentsBlock,
    DashboardLesson,
    DashboardLessonsBlock,
    DashboardOwner,
    DashboardReviewBlock,
    DashboardReviewItem,
    DashboardStaff,
    DashboardUnmarkedBlock,
    DashboardUnmarkedLesson,
)
from src.services.auth import STAFF_ROLES


class DashboardService:
    """Собирает дашборд «Сегодня» для сотрудника."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис на сессию текущей единицы работы."""
        self._dashboard = DashboardRepository(session)
        self._finance = FinanceRepository(session)

    async def get_today_dashboard(
        self, actor: CurrentUser, now: datetime | None = None
    ) -> DashboardStaff:
        """Дашборд на сегодня; у владельца — ``DashboardOwner`` с суммами за месяц.

        Raises:
            PermissionDeniedError: Не сотрудник.
        """
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        moment = now or utcnow()
        today = local_date_of(moment, actor.timezone)
        day_start, day_end = day_bounds_utc(today, actor.timezone)
        staff = DashboardStaff(
            date=today,
            timezone=actor.timezone,
            lessons=await self._lessons_block(day_start, day_end, moment),
            review_queue=await self._review_block(),
            unsubmitted=await self._unsubmitted_block(day_start, day_end),
            unmarked_lessons=await self._unmarked_block(moment),
            deadlines=await self._deadlines_block(moment),
        )
        if actor.role != UserRole.OWNER:
            return staff
        month_start, month_end = month_bounds_utc(today, actor.timezone)
        return DashboardOwner(
            **staff.model_dump(),
            earned_month=await self._finance.earned_between(month_start, month_end),
            expected_month=await self._finance.expected_between(month_start, month_end),
        )

    # ------------------------------------------------------------------ блоки

    async def _lessons_block(
        self, start: datetime, end: datetime, now: datetime
    ) -> DashboardLessonsBlock:
        rows, total = await self._dashboard.lessons_between(start, end, limit=DASHBOARD_LESSONS_MAX)
        names = await self._dashboard.student_names([row.id for row in rows])
        return DashboardLessonsBlock(
            total=total,
            items=[
                DashboardLesson(
                    id=row.id,
                    subject_code=row.subject_code,
                    start_at=row.start_at,
                    end_at=row.end_at,
                    status=row.status,
                    student_names=names.get(row.id, []),
                    needs_mark=row.status == LessonStatus.SCHEDULED and row.end_at <= now,
                )
                for row in rows
            ],
        )

    async def _review_block(self) -> DashboardReviewBlock:
        rows, total = await self._dashboard.review_queue(limit=DASHBOARD_TOP_ITEMS)
        return DashboardReviewBlock(
            total=total,
            items=[
                DashboardReviewItem(
                    assignment_id=row.assignment_id,
                    student_name=row.student_name,
                    title=row.title,
                    submitted_at=row.submitted_at,
                )
                for row in rows
            ],
        )

    async def _unsubmitted_block(self, start: datetime, end: datetime) -> DashboardAssignmentsBlock:
        rows, total = await self._dashboard.unsubmitted_for_lessons(
            start, end, limit=DASHBOARD_TOP_ITEMS
        )
        return self._assignments(rows, total)

    async def _deadlines_block(self, now: datetime) -> DashboardAssignmentsBlock:
        rows, total = await self._dashboard.deadlines_between(
            now, now + timedelta(hours=DASHBOARD_DEADLINE_HOURS), limit=DASHBOARD_TOP_ITEMS
        )
        return self._assignments(rows, total)

    async def _unmarked_block(self, now: datetime) -> DashboardUnmarkedBlock:
        rows, total = await self._dashboard.unmarked_lessons(
            now - timedelta(days=UNMARKED_LESSON_LOOKBACK_DAYS), now, limit=DASHBOARD_TOP_ITEMS
        )
        names = await self._dashboard.student_names([row.id for row in rows])
        return DashboardUnmarkedBlock(
            total=total,
            items=[
                DashboardUnmarkedLesson(
                    id=row.id,
                    subject_code=row.subject_code,
                    start_at=row.start_at,
                    student_names=names.get(row.id, []),
                )
                for row in rows
            ],
        )

    @staticmethod
    def _assignments(rows: list[AssignmentRow], total: int) -> DashboardAssignmentsBlock:
        return DashboardAssignmentsBlock(
            total=total,
            items=[
                DashboardAssignmentItem(
                    assignment_id=row.assignment_id,
                    student_id=row.student_id,
                    student_name=row.student_name,
                    title=row.title,
                    status=row.status,
                    due_at=row.due_at,
                )
                for row in rows
            ],
        )
