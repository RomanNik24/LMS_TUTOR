"""Схемы дашборда «Сегодня» (docs/01 §4.3, docs/08 §5.1).

Две схемы: у менеджера финансовых полей нет вообще, у владельца добавлены ``earned_month`` и
``expected_month`` (docs/08 §8). Пустой блок — это ``total = 0`` и пустой список.
"""

from datetime import date, datetime

from pydantic import BaseModel

from src.core.enums import AssignmentStatus, LessonStatus, UserRole
from src.schemas.roles import audience_config


class DashboardLesson(BaseModel):
    """Урок сегодня; ``needs_mark`` — он уже закончился, а отметки о проведении нет."""

    id: int
    subject_code: str
    start_at: datetime
    end_at: datetime
    status: LessonStatus
    student_names: list[str]
    needs_mark: bool


class DashboardReviewItem(BaseModel):
    """Работа в очереди проверки."""

    assignment_id: int
    student_name: str
    title: str
    submitted_at: datetime | None


class DashboardAssignmentItem(BaseModel):
    """Несданная или скоро истекающая выдача."""

    assignment_id: int
    student_id: int
    student_name: str
    title: str
    status: AssignmentStatus
    due_at: datetime


class DashboardUnmarkedLesson(BaseModel):
    """Прошедший урок без отметки о проведении."""

    id: int
    subject_code: str
    start_at: datetime
    student_names: list[str]


class DashboardLessonsBlock(BaseModel):
    """Блок «Уроки сегодня»."""

    total: int
    items: list[DashboardLesson]


class DashboardReviewBlock(BaseModel):
    """Блок «ДЗ на проверку»: общее число и самые давние работы."""

    total: int
    items: list[DashboardReviewItem]


class DashboardAssignmentsBlock(BaseModel):
    """Блок выдач: общее число и ближайшие по сроку."""

    total: int
    items: list[DashboardAssignmentItem]


class DashboardUnmarkedBlock(BaseModel):
    """Блок «Уроки без отметки»."""

    total: int
    items: list[DashboardUnmarkedLesson]


class DashboardStaff(BaseModel):
    """Дашборд для менеджера: без финансовых полей."""

    model_config = audience_config(UserRole.MANAGER)

    date: date
    timezone: str
    lessons: DashboardLessonsBlock
    review_queue: DashboardReviewBlock
    unsubmitted: DashboardAssignmentsBlock
    unmarked_lessons: DashboardUnmarkedBlock
    deadlines: DashboardAssignmentsBlock


class DashboardOwner(DashboardStaff):
    """Дашборд для владельца: плюс заработок текущего месяца (рубли)."""

    model_config = audience_config(UserRole.OWNER)

    earned_month: int
    expected_month: int
