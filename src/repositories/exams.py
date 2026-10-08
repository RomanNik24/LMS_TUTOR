"""Репозитории шкал и результатов пробных экзаменов (docs/04 §1.3, §6)."""

from sqlalchemy import func, select

from src.db.models import GradeScale
from src.repositories.base import BaseRepository


class GradeScaleRepository(BaseRepository[GradeScale]):
    """Доступ к таблице ``grade_scales`` (шкалы не хардкодятся: читаются из БД)."""

    async def lookup(
        self, exam_type_id: int, exam_year: int, primary_score: int
    ) -> tuple[int, int] | None:
        """Значение шкалы для первичного балла.

        Берётся шкала с наибольшим ``valid_year <= exam_year`` для этого типа экзамена
        (docs/04 §1.3).

        Returns:
            ``(год шкалы, результат)`` или ``None``: подходящей шкалы нет либо в ней нет такого
            первичного балла.
        """
        latest = (
            select(func.max(GradeScale.valid_year))
            .where(GradeScale.exam_type_id == exam_type_id, GradeScale.valid_year <= exam_year)
            .scalar_subquery()
        )
        stmt = select(GradeScale.valid_year, GradeScale.result_value).where(
            GradeScale.exam_type_id == exam_type_id,
            GradeScale.valid_year == latest,
            GradeScale.primary_score == primary_score,
        )
        row = (await self._session.execute(stmt)).one_or_none()
        return None if row is None else (int(row[0]), int(row[1]))
