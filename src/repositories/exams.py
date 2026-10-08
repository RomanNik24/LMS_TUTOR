"""Репозитории шкал и результатов пробных экзаменов (docs/04 §1.3, §6)."""

from typing import Any, cast

from sqlalchemy import Select, func, select

from src.db.models import ExamType, GradeScale, MockExamResult, User
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


class MockExamRepository(BaseRepository[MockExamResult]):
    """Доступ к таблице ``mock_exam_results`` (docs/04 §6)."""

    @staticmethod
    def _joined() -> Select[Any]:
        stmt = (
            select(MockExamResult, ExamType, User.display_name)
            .join(ExamType, ExamType.id == MockExamResult.exam_type_id)
            .join(User, User.id == MockExamResult.student_id)
        )
        return cast("Select[Any]", stmt)

    async def get_by_id(self, result_id: int, *, for_update: bool = False) -> MockExamResult | None:
        """Результат по id; ``for_update`` блокирует строку на время транзакции."""
        stmt = select(MockExamResult).where(MockExamResult.id == result_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_assignment(self, assignment_id: int) -> MockExamResult | None:
        """Результат, созданный из выдачи ДЗ (``assignment_id`` уникален)."""
        stmt = (
            select(MockExamResult)
            .where(MockExamResult.assignment_id == assignment_id)
            .with_for_update()
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def row(self, result_id: int) -> tuple[MockExamResult, ExamType, str] | None:
        """Результат с типом экзамена и именем ученика одним запросом."""
        stmt = self._joined().where(MockExamResult.id == result_id)
        found = (await self._session.execute(stmt)).one_or_none()
        return None if found is None else (found[0], found[1], found[2])

    async def page(
        self,
        *,
        student_id: int | None,
        exam_type_id: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[MockExamResult, ExamType, str]], int]:
        """Страница результатов (новые экзамены первыми) и общее число."""
        conditions = []
        if student_id is not None:
            conditions.append(MockExamResult.student_id == student_id)
        if exam_type_id is not None:
            conditions.append(MockExamResult.exam_type_id == exam_type_id)
        total = (
            await self._session.execute(
                select(func.count()).select_from(MockExamResult).where(*conditions)
            )
        ).scalar_one()
        stmt = (
            self._joined()
            .where(*conditions)
            .order_by(MockExamResult.exam_date.desc(), MockExamResult.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = [(r[0], r[1], r[2]) for r in (await self._session.execute(stmt)).all()]
        return rows, int(total)

    async def delete(self, entity: MockExamResult) -> None:
        """Удалить результат."""
        await self._session.delete(entity)
        await self._session.flush()
