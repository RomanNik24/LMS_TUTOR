"""``ExamService``: пробные экзамены и перевод первичных баллов (docs/04 §6, docs/01 US-06).

Шкалы НЕ хардкодятся: значение берётся из ``grade_scales`` по году экзамена (docs/04 §1.3).
Правила (docs/04 §6):
1. ``max_primary`` результата отличается от ``exam_types.max_primary`` — конвертация не
   применяется (``converted_value = NULL``);
2. иначе значение — из шкалы с наибольшим ``valid_year <= год экзамена``;
3. ОГЭ математика: ``geometry_score < config.min_geometry`` → итоговая оценка 2 при любой сумме;
   если баллы по геометрии не указаны, расчёт по сумме и предупреждение.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ExamType
from src.repositories.exams import GradeScaleRepository
from src.schemas.exams import ConversionWarning, ScoreConversion

MIN_PASSING_GRADE = 2


class ExamService:
    """Конвертация баллов пробников (записи результатов — T6.03)."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис на сессию текущей единицы работы."""
        self._session = session
        self._scales = GradeScaleRepository(session)

    async def convert_score(
        self,
        exam_type: ExamType,
        *,
        exam_date: date,
        primary_score: int,
        max_primary: int,
        geometry_score: int | None = None,
    ) -> ScoreConversion:
        """Перевести первичный балл в оценку или тестовый балл.

        Args:
            exam_type: Тип экзамена (с ``max_primary`` и ``config``).
            exam_date: Дата экзамена: по её году выбирается шкала.
            primary_score: Первичный балл.
            max_primary: Максимум этого варианта.
            geometry_score: Баллы по геометрии (только ОГЭ математика).
        """
        if max_primary != exam_type.max_primary:
            return ScoreConversion(converted_value=None, scale_year=None, scale_applicable=False)
        found = await self._scales.lookup(exam_type.id, exam_date.year, primary_score)
        if found is None:
            return ScoreConversion(converted_value=None, scale_year=None, scale_applicable=False)
        scale_year, value = found
        warning: ConversionWarning | None = None
        min_geometry = exam_type.config.get("min_geometry")
        if isinstance(min_geometry, int):
            if geometry_score is None:
                warning = ConversionWarning.GEOMETRY_MISSING
            elif geometry_score < min_geometry:
                value = min(value, MIN_PASSING_GRADE)
        return ScoreConversion(
            converted_value=value, scale_year=scale_year, scale_applicable=True, warning=warning
        )
