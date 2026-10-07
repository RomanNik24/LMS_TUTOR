"""Репозитории домашних заданий, выдач, материалов и файлов (docs/04 §5)."""

from datetime import datetime

from sqlalchemy import case, func, select, update

from src.core.enums import AssignmentStatus, HomeworkFileRole
from src.db.models import (
    ExamType,
    Homework,
    HomeworkAssignment,
    HomeworkFile,
    HomeworkMaterial,
    Subject,
    User,
)
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

    async def list_page(
        self, *, limit: int, offset: int
    ) -> tuple[list[tuple[Homework, str, int, int]], int]:
        """Страница заданий (новые сверху) с кодом предмета и счётчиками «выдано / сдано».

        «Сдано» — выдачи в статусах ``submitted`` и ``graded``.
        """
        submitted = func.coalesce(
            func.sum(
                case(
                    (
                        HomeworkAssignment.status.in_(
                            [AssignmentStatus.SUBMITTED, AssignmentStatus.GRADED]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        stmt = (
            select(Homework, Subject.code, func.count(HomeworkAssignment.id), submitted)
            .join(Subject, Subject.id == Homework.subject_id)
            .outerjoin(HomeworkAssignment, HomeworkAssignment.homework_id == Homework.id)
            .group_by(Homework.id, Subject.code)
            .order_by(Homework.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = [
            (row[0], row[1], int(row[2]), int(row[3]))
            for row in (await self._session.execute(stmt)).all()
        ]
        total = (
            await self._session.execute(select(func.count()).select_from(Homework))
        ).scalar_one()
        return rows, total

    async def subject_code(self, subject_id: int) -> str:
        """Код предмета задания."""
        stmt = select(Subject.code).where(Subject.id == subject_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def assignments_with_names(
        self, homework_id: int
    ) -> list[tuple[HomeworkAssignment, str]]:
        """Выдачи задания вместе с именами учеников, по возрастанию id."""
        stmt = (
            select(HomeworkAssignment, User.display_name)
            .join(User, User.id == HomeworkAssignment.student_id)
            .where(HomeworkAssignment.homework_id == homework_id)
            .order_by(HomeworkAssignment.id)
        )
        return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

    async def materials(self, homework_id: int) -> list[HomeworkMaterial]:
        """Материалы задания по возрастанию id."""
        stmt = (
            select(HomeworkMaterial)
            .where(HomeworkMaterial.homework_id == homework_id)
            .order_by(HomeworkMaterial.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def assigned_student_ids(self, homework_id: int) -> set[int]:
        """Ученики, которым задание уже выдано."""
        stmt = select(HomeworkAssignment.student_id).where(
            HomeworkAssignment.homework_id == homework_id
        )
        return set((await self._session.execute(stmt)).scalars())

    async def first_original_due(self, homework_id: int) -> datetime | None:
        """Самый ранний первоначальный срок среди выдач (для добавления учеников к fixed)."""
        stmt = select(func.min(HomeworkAssignment.original_due_at)).where(
            HomeworkAssignment.homework_id == homework_id
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def add_assignments(self, rows: list[HomeworkAssignment]) -> None:
        """Добавить выдачи пачкой."""
        self._session.add_all(rows)
        await self._session.flush()


class ExamTypeRepository(BaseRepository[ExamType]):
    """Доступ к справочнику ``exam_types``."""

    async def get_by_id(self, exam_type_id: int) -> ExamType | None:
        """Тип экзамена по id."""
        stmt = select(ExamType).where(ExamType.id == exam_type_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()


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

    async def expire_due(self, now: datetime, max_extensions: int) -> list[int]:
        """Перевести просроченные выдачи в ``expired`` одним запросом; вернуть их id.

        Условие (docs/04 §5.4): ``now > due_at``, переносы исчерпаны и статус ``assigned`` или
        ``needs_revision``. Условие повторно проверяется самой БД при обновлении, поэтому
        параллельная оценка или сдача не потеряются, а повторный запуск ничего не меняет.
        """
        stmt = (
            update(HomeworkAssignment)
            .where(
                HomeworkAssignment.due_at < now,
                HomeworkAssignment.extensions_count >= max_extensions,
                HomeworkAssignment.status.in_(
                    [AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION]
                ),
            )
            .values(status=AssignmentStatus.EXPIRED, expired_at=now, updated_at=now)
            .returning(HomeworkAssignment.id)
            .execution_options(synchronize_session=False)
        )
        return sorted((await self._session.execute(stmt)).scalars())


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
