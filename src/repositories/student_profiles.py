"""Репозиторий профилей учеников (задача T1.06, docs/04 §2.2)."""

from collections.abc import Sequence

from sqlalchemy import func, select

from src.core.enums import UserRole
from src.db.models import StudentProfile, User
from src.repositories.base import BaseRepository


def escape_like(text: str) -> str:
    """Экранировать ``%``, ``_`` и ``\\`` для ``LIKE ... ESCAPE '\\'``."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class StudentProfileRepository(BaseRepository[StudentProfile]):
    """Доступ к таблице ``student_profiles``."""

    async def get_by_user_id(self, user_id: int) -> StudentProfile | None:
        """Найти профиль ученика по ``user_id``.

        Args:
            user_id: ``student_profiles.user_id`` (он же ``users.id``).

        Returns:
            Профиль или ``None``.
        """
        stmt = select(StudentProfile).where(StudentProfile.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def search(
        self, *, is_active: bool, q: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[User, StudentProfile]], int]:
        """Список учеников со страницей и общим числом (docs/08 §5.2).

        Args:
            is_active: ``True`` — активные, ``False`` — архив.
            q: Подстрока имени (без учёта регистра) или ``None``.
            limit: Размер страницы.
            offset: Смещение.

        Returns:
            Пары (пользователь, профиль) по алфавиту имени и общее число подходящих.
        """
        conditions = [User.role == UserRole.STUDENT, User.is_active.is_(is_active)]
        if q:
            conditions.append(User.display_name.ilike(f"%{escape_like(q)}%", escape="\\"))
        total_stmt = (
            select(func.count(User.id))
            .join(StudentProfile, StudentProfile.user_id == User.id)
            .where(*conditions)
        )
        total = int((await self._session.execute(total_stmt)).scalar_one())
        page_stmt = (
            select(User, StudentProfile)
            .join(StudentProfile, StudentProfile.user_id == User.id)
            .where(*conditions)
            .order_by(User.display_name, User.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(page_stmt)).all()
        return [(user, profile) for user, profile in rows], total

    async def prices_for(self, student_ids: Sequence[int]) -> dict[int, int]:
        """Текущая цена занятия (рубли) для нескольких учеников одним запросом."""
        if not student_ids:
            return {}
        stmt = select(StudentProfile.user_id, StudentProfile.lesson_price).where(
            StudentProfile.user_id.in_(list(student_ids))
        )
        return {row[0]: row[1] for row in (await self._session.execute(stmt)).all()}
