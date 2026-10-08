"""Схемы справочников (docs/08 §3): предметы и типы экзаменов, только чтение."""

from pydantic import BaseModel, ConfigDict

from src.core.enums import ExamKind, ExamResultKind


class SubjectItem(BaseModel):
    """Предмет: код (в запросах API) и отображаемое имя."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class ExamTypeItem(BaseModel):
    """Тип экзамена: код, предмет, вид (ОГЭ/ЕГЭ), формат результата и максимальный балл."""

    id: int
    code: str
    subject_code: str
    kind: ExamKind
    result_kind: ExamResultKind
    max_primary: int
    name: str
    # есть правило «баллы по геометрии» (ОГЭ математика): форма показывает поле геометрии
    uses_geometry: bool
