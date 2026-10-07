"""Репозитории предметов и связи ученик ↔ предмет (docs/04 §1.1, §2.3)."""

from collections.abc import Collection, Sequence

from sqlalchemy import delete, select

from src.db.models import StudentSubject, Subject
from src.repositories.base import BaseRepository


class SubjectRepository(BaseRepository[Subject]):
    """Доступ к таблице ``subjects``."""

    async def active_by_codes(self, codes: Collection[str]) -> list[Subject]:
        """Найти активные предметы по кодам.

        Args:
            codes: Коды предметов (``informatics``, ``math``).

        Returns:
            Найденные предметы (не обязательно все запрошенные).
        """
        if not codes:
            return []
        stmt = select(Subject).where(Subject.code.in_(list(codes)), Subject.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars())

    async def list_active(self) -> list[Subject]:
        """Активные предметы в порядке ``id`` (справочник ``GET /reference/subjects``)."""
        stmt = select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.id)
        return list((await self._session.execute(stmt)).scalars())


class StudentSubjectRepository(BaseRepository[StudentSubject]):
    """Доступ к таблице ``student_subjects``."""

    async def codes_for(self, student_ids: Sequence[int]) -> dict[int, list[str]]:
        """Коды предметов для нескольких учеников одним запросом.

        Args:
            student_ids: ``users.id`` учеников.

        Returns:
            ``{student_id: [коды по алфавиту]}``; у учеников без предметов — пустой список.
        """
        result: dict[int, list[str]] = {student_id: [] for student_id in student_ids}
        if not student_ids:
            return result
        stmt = (
            select(StudentSubject.student_id, Subject.code)
            .join(Subject, Subject.id == StudentSubject.subject_id)
            .where(StudentSubject.student_id.in_(list(student_ids)))
            .order_by(Subject.code)
        )
        for student_id, code in (await self._session.execute(stmt)).all():
            result[student_id].append(code)
        return result

    async def replace(self, student_id: int, subject_ids: Collection[int]) -> None:
        """Заменить набор предметов ученика (без commit).

        Args:
            student_id: ``users.id`` ученика.
            subject_ids: Новый набор ``subjects.id``.
        """
        await self._session.execute(
            delete(StudentSubject).where(StudentSubject.student_id == student_id)
        )
        for subject_id in sorted(set(subject_ids)):
            self._session.add(StudentSubject(student_id=student_id, subject_id=subject_id))
        await self._session.flush()
