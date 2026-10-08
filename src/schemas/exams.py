"""Схемы пробных экзаменов (docs/04 §6, docs/08 §5.6)."""

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core import texts


class ConversionWarning(StrEnum):
    """Предупреждение конвертации (результат всё равно посчитан)."""

    # ОГЭ математика: баллы по геометрии не указаны, расчёт только по сумме (docs/04 §6, п. 3)
    GEOMETRY_MISSING = "geometry_missing"


class ScoreConversion(BaseModel):
    """Результат перевода первичного балла по шкале.

    ``scale_applicable = false`` — шкала неприменима (нестандартный максимум варианта или шкалы
    нет): тогда ``converted_value`` и ``scale_year`` пусты, интерфейс показывает процент.
    """

    converted_value: int | None
    scale_year: int | None
    scale_applicable: bool
    warning: ConversionWarning | None = None


MAX_PRIMARY_LIMIT = 1000
COMMENT_MAX_LENGTH = 2000


class ConvertRequest(BaseModel):
    """Предпросмотр конвертации в форме ввода пробника (без сохранения)."""

    model_config = ConfigDict(extra="forbid")

    exam_type_id: int
    exam_date: date
    primary_score: int = Field(ge=0, le=MAX_PRIMARY_LIMIT)
    max_primary: int = Field(ge=1, le=MAX_PRIMARY_LIMIT)
    geometry_score: int | None = Field(default=None, ge=0, le=MAX_PRIMARY_LIMIT)


class MockExamCreate(ConvertRequest):
    """Ручной ввод результата пробника без ДЗ (docs/08 §5.6)."""

    student_id: int
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)

    @field_validator("comment")
    @classmethod
    def _comment(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else value.strip()


class MockExamUpdate(BaseModel):
    """Исправление ручного результата; ученика и тип экзамена менять нельзя."""

    model_config = ConfigDict(extra="forbid")

    exam_date: date | None = None
    primary_score: int | None = Field(default=None, ge=0, le=MAX_PRIMARY_LIMIT)
    max_primary: int | None = Field(default=None, ge=1, le=MAX_PRIMARY_LIMIT)
    # geometry_score и comment можно очистить, передав null явно (поле в model_fields_set)
    geometry_score: int | None = Field(default=None, ge=0, le=MAX_PRIMARY_LIMIT)
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(texts.MOCK_EXAM_UPDATE_EMPTY)
        return self


class MockExamItem(BaseModel):
    """Результат пробника в ответах для персонала (денег и заметок преподавателя нет)."""

    id: int
    student_id: int
    student_name: str
    exam_type_id: int
    exam_type_code: str
    exam_type_name: str
    exam_date: date
    primary_score: int
    max_primary: int
    geometry_score: int | None
    converted_value: int | None
    scale_year: int | None
    scale_applicable: bool
    warning: ConversionWarning | None
    assignment_id: int | None
    comment: str | None


class MockExamPage(BaseModel):
    """Страница списка результатов (docs/08 §1)."""

    items: list[MockExamItem]
    total: int
    limit: int
    offset: int
