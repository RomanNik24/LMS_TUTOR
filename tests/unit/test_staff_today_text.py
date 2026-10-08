"""Текст ``/today`` для персонала (T7.03): блоки дашборда без финансов."""

from datetime import UTC, date, datetime

from src.bot.handlers.schedule import _staff_text
from src.core.enums import AssignmentStatus, LessonStatus
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
)

MOMENT = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
EMPTY_ASSIGNMENTS = DashboardAssignmentsBlock(total=0, items=[])


def make(
    *,
    lessons: DashboardLessonsBlock | None = None,
    review_queue: DashboardReviewBlock | None = None,
    unsubmitted: DashboardAssignmentsBlock | None = None,
) -> DashboardStaff:
    return DashboardStaff(
        date=date(2026, 10, 6),
        timezone="Europe/Moscow",
        lessons=lessons or DashboardLessonsBlock(total=0, items=[]),
        review_queue=review_queue or DashboardReviewBlock(total=0, items=[]),
        unsubmitted=unsubmitted or EMPTY_ASSIGNMENTS,
        unmarked_lessons=DashboardUnmarkedBlock(total=0, items=[]),
        deadlines=EMPTY_ASSIGNMENTS,
    )


def test_empty_day_has_no_text() -> None:
    assert _staff_text(make()) is None


def test_blocks_are_rendered_in_order_without_money() -> None:
    lesson = DashboardLesson(
        id=1,
        subject_code="informatics",
        start_at=MOMENT,
        end_at=MOMENT,
        status=LessonStatus.SCHEDULED,
        student_names=["Аня"],
        needs_mark=False,
    )
    pending = DashboardAssignmentItem(
        assignment_id=7,
        student_id=2,
        student_name="Борис",
        title="Графы",
        status=AssignmentStatus.ASSIGNED,
        due_at=MOMENT,
    )
    dashboard = make(
        lessons=DashboardLessonsBlock(total=1, items=[lesson]),
        review_queue=DashboardReviewBlock(
            total=2,
            items=[
                DashboardReviewItem(
                    assignment_id=1, student_name="Аня", title="Сети", submitted_at=MOMENT
                )
            ],
        ),
        unsubmitted=DashboardAssignmentsBlock(total=1, items=[pending]),
    )

    text = _staff_text(dashboard)

    assert text is not None
    assert text.startswith("Сегодня, вт, 6 окт:\n15:00 Информатика: Аня")
    assert "ДЗ на проверку: 2" in text
    assert "Не сдано к сегодняшним урокам (1):" in text
    assert "Борис — Графы" in text
    assert "₽" not in text


def test_owner_dashboard_money_is_not_rendered_in_bot_text() -> None:
    staff = make()
    owner = DashboardOwner(**staff.model_dump(), earned_month=5000, expected_month=7000)

    assert _staff_text(owner) is None
