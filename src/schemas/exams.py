"""Схемы пробных экзаменов (docs/04 §6, docs/08 §5.6)."""

from enum import StrEnum

from pydantic import BaseModel


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
