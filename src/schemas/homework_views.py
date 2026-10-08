"""Схемы просмотра выдач: для ученика и для персонала (docs/08 §4, §5.5, T4.11).

В схемах ученика нет заметок преподавателя, денег и данных других учеников. Журнал переносов
ученик не видит вовсе, только число оставшихся переносов.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from src.core.enums import AssignmentStatus, HomeworkKind, SubmissionType
from src.schemas.files import HomeworkFileItem, MaterialItem


class StudentHomeworkFilter(StrEnum):
    """Фильтр списка ДЗ ученика: ``status=active|submitted|graded|expired`` (docs/08 §4)."""

    ACTIVE = "active"
    SUBMITTED = "submitted"
    GRADED = "graded"
    EXPIRED = "expired"


class StudentAssignmentItem(BaseModel):
    """Строка списка ДЗ ученика."""

    assignment_id: int
    homework_id: int
    title: str
    kind: HomeworkKind
    subject_code: str
    status: AssignmentStatus
    due_at: datetime
    is_overdue: bool
    extensions_left: int
    max_score: int
    score: int | None
    score_percent: int | None
    submitted_at: datetime | None


class StudentAssignmentPage(BaseModel):
    """Страница списка ДЗ ученика."""

    items: list[StudentAssignmentItem]
    total: int
    limit: int
    offset: int


class StudentAssignmentDetail(StudentAssignmentItem):
    """Карточка ДЗ ученика: описание, материалы, оценка, комментарии, файлы."""

    description: str | None
    original_due_at: datetime
    on_time: bool | None
    submission_type: SubmissionType | None
    student_comment: str | None
    teacher_comment: str | None
    materials: list[MaterialItem]
    files: list[HomeworkFileItem]


class AdminAssignmentItem(BaseModel):
    """Строка списка выдач для персонала."""

    assignment_id: int
    homework_id: int
    title: str
    kind: HomeworkKind
    # тип экзамена пробника: по нему экран проверки показывает конвертацию (docs/07 §9.2.9)
    exam_type_id: int | None
    student_id: int
    student_name: str
    status: AssignmentStatus
    due_at: datetime
    is_overdue: bool
    extensions_count: int
    submitted_at: datetime | None
    score: int | None
    max_score: int


class AdminAssignmentPage(BaseModel):
    """Страница списка выдач для персонала."""

    items: list[AdminAssignmentItem]
    total: int
    limit: int
    offset: int


class ExtensionLogItem(BaseModel):
    """Запись журнала переносов (только персоналу)."""

    old_due_at: datetime
    new_due_at: datetime
    created_by: int
    created_at: datetime


class AdminAssignmentDetail(AdminAssignmentItem):
    """Карточка выдачи для персонала: файлы ученика, журнал переносов, комментарии."""

    description: str | None
    original_due_at: datetime
    on_time: bool | None
    submission_type: SubmissionType | None
    student_comment: str | None
    teacher_comment: str | None
    graded_after_expiry: bool
    score_percent: int | None
    materials: list[MaterialItem]
    files: list[HomeworkFileItem]
    extensions: list[ExtensionLogItem]
