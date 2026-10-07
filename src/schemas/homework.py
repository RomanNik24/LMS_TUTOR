"""Схемы домашних заданий для персонала (docs/04 §5, docs/08 §5.5, T4.06).

Финансовых полей нет: задание и выдача видны персоналу целиком, но деньги к ним не относятся.
"""

from datetime import datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core import texts
from src.core.enums import AssignmentStatus, DueMode, HomeworkKind, SubmissionType
from src.schemas.files import MaterialItem

TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 5000
MAX_SCORE_LIMIT = 200
MAX_ASSIGNEES = 100


class HomeworkCreate(BaseModel):
    """Создание задания и выдача ученикам: одно ``homework`` и N выдач.

    ``regular``: обязательны ``subject_code`` и ``max_score`` (число заданий, 1 задание = 1 балл).
    ``mock_exam``: обязателен ``exam_type_id``; предмет берётся из экзамена, ``max_score`` по
    умолчанию — максимальный первичный балл экзамена.
    ``due_mode = fixed``: обязателен ``due_at``. ``next_lesson``: срок — начало ближайшего урока
    ученика; ``due_at`` в этом случае — запасной срок для учеников без запланированного урока.
    """

    model_config = ConfigDict(extra="forbid")

    kind: HomeworkKind
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    subject_code: str | None = Field(default=None, min_length=1, max_length=32)
    exam_type_id: int | None = None
    max_score: int | None = Field(default=None, ge=1, le=MAX_SCORE_LIMIT)
    lesson_id: int | None = None
    due_mode: DueMode
    due_at: AwareDatetime | None = None
    student_ids: list[int] = Field(min_length=1, max_length=MAX_ASSIGNEES)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError(texts.HOMEWORK_TITLE_REQUIRED)
        return stripped

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else value.strip()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind == HomeworkKind.MOCK_EXAM and self.exam_type_id is None:
            raise ValueError(texts.HOMEWORK_EXAM_TYPE_REQUIRED)
        if self.kind == HomeworkKind.REGULAR:
            if self.subject_code is None:
                raise ValueError(texts.HOMEWORK_SUBJECT_REQUIRED)
            if self.max_score is None:
                raise ValueError(texts.HOMEWORK_MAX_SCORE_REQUIRED)
        if self.due_mode == DueMode.FIXED and self.due_at is None:
            raise ValueError(texts.HOMEWORK_DUE_AT_REQUIRED)
        if len(set(self.student_ids)) != len(self.student_ids):
            raise ValueError(texts.LESSON_STUDENTS_DUPLICATE)
        return self


class AssigneesAdd(BaseModel):
    """Добавление учеников к существующему заданию."""

    model_config = ConfigDict(extra="forbid")

    student_ids: list[int] = Field(min_length=1, max_length=MAX_ASSIGNEES)
    due_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len(set(self.student_ids)) != len(self.student_ids):
            raise ValueError(texts.LESSON_STUDENTS_DUPLICATE)
        return self


class AssignmentItem(BaseModel):
    """Выдача ученику в карточке задания."""

    id: int
    student_id: int
    display_name: str
    status: AssignmentStatus
    original_due_at: datetime
    due_at: datetime
    extensions_count: int


class HomeworkItem(BaseModel):
    """Задание со всеми выдачами и материалами."""

    id: int
    kind: HomeworkKind
    title: str
    description: str | None
    subject_code: str
    exam_type_id: int | None
    lesson_id: int | None
    max_score: int
    due_mode: DueMode
    created_at: datetime
    materials: list[MaterialItem]
    assignments: list[AssignmentItem]


class HomeworkListItem(BaseModel):
    """Строка списка заданий: «сдали N из M»."""

    id: int
    kind: HomeworkKind
    title: str
    subject_code: str
    max_score: int
    created_at: datetime
    assigned_count: int
    submitted_count: int


class HomeworkListPage(BaseModel):
    """Страница списка заданий (docs/08 §1)."""

    items: list[HomeworkListItem]
    total: int
    limit: int
    offset: int


STUDENT_COMMENT_MAX_LENGTH = 2000


class SubmitRequest(BaseModel):
    """Сдача работы: необязательный комментарий ученика."""

    model_config = ConfigDict(extra="forbid")

    student_comment: str | None = Field(default=None, max_length=STUDENT_COMMENT_MAX_LENGTH)

    @field_validator("student_comment")
    @classmethod
    def _comment(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else value.strip()


class SubmissionItem(BaseModel):
    """Итог сдачи для ученика: статус, тип сдачи и признак «в срок»."""

    assignment_id: int
    status: AssignmentStatus
    submission_type: SubmissionType
    submitted_at: datetime
    on_time: bool
    files_count: int
