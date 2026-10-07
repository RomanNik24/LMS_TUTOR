"""Репозитории домашних заданий, выдач, материалов и файлов (docs/04 §5)."""

from sqlalchemy import func, select

from src.core.enums import HomeworkFileRole
from src.db.models import Homework, HomeworkAssignment, HomeworkFile, HomeworkMaterial
from src.repositories.base import BaseRepository


class HomeworkRepository(BaseRepository[Homework]):
    """Доступ к таблице ``homeworks``."""

    async def get_by_id(self, homework_id: int) -> Homework | None:
        """Задание по id."""
        stmt = select(Homework).where(Homework.id == homework_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def student_has_assignment(self, homework_id: int, student_id: int) -> bool:
        """Есть ли у ученика выдача этого задания."""
        stmt = select(HomeworkAssignment.id).where(
            HomeworkAssignment.homework_id == homework_id,
            HomeworkAssignment.student_id == student_id,
        )
        return (await self._session.execute(stmt)).first() is not None


class HomeworkAssignmentRepository(BaseRepository[HomeworkAssignment]):
    """Доступ к таблице ``homework_assignments``."""

    async def get_by_id(
        self, assignment_id: int, *, for_update: bool = False
    ) -> HomeworkAssignment | None:
        """Выдача по id; ``for_update`` блокирует строку на время транзакции."""
        stmt = select(HomeworkAssignment).where(HomeworkAssignment.id == assignment_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()


class HomeworkFileRepository(BaseRepository[HomeworkFile]):
    """Доступ к таблице ``homework_files``."""

    async def get_by_id(self, file_id: int) -> HomeworkFile | None:
        """Файл по id."""
        stmt = select(HomeworkFile).where(HomeworkFile.id == file_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_for(self, assignment_id: int, role: HomeworkFileRole) -> int:
        """Сколько файлов с ролью у выдачи."""
        stmt = (
            select(func.count())
            .select_from(HomeworkFile)
            .where(HomeworkFile.assignment_id == assignment_id, HomeworkFile.role == role)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def delete(self, entity: HomeworkFile) -> None:
        """Удалить запись о файле (объект в S3 удаляет сервис)."""
        await self._session.delete(entity)
        await self._session.flush()


class HomeworkMaterialRepository(BaseRepository[HomeworkMaterial]):
    """Доступ к таблице ``homework_materials``."""

    async def get_by_id(self, material_id: int) -> HomeworkMaterial | None:
        """Материал по id."""
        stmt = select(HomeworkMaterial).where(HomeworkMaterial.id == material_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
