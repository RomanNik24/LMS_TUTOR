"""Репозиторий профилей учеников (задача T1.06, docs/04 §2.2)."""

from sqlalchemy import select

from src.db.models import StudentProfile
from src.repositories.base import BaseRepository


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
