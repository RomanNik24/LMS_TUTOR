"""Репозиторий пользователей (задача T1.06, docs/04 §2.1, docs/08 §2)."""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.models import User
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Доступ к таблице ``users`` (методы, нужные для авторизации)."""

    async def get_by_id(self, user_id: int, *, with_profile: bool = False) -> User | None:
        """Найти пользователя по id (зависимость ``current_user``).

        Args:
            user_id: ``users.id``.
            with_profile: Сразу загрузить ``student_profile`` (selectinload).

        Returns:
            Пользователь или ``None``.
        """
        stmt = select(User).where(User.id == user_id)
        if with_profile:
            stmt = stmt.options(selectinload(User.student_profile))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_telegram_id(
        self, telegram_id: int, *, with_profile: bool = False
    ) -> User | None:
        """Найти пользователя по Telegram ID (вход, принятие приглашения).

        Args:
            telegram_id: Telegram ID (BIGINT).
            with_profile: Сразу загрузить ``student_profile`` (selectinload).

        Returns:
            Пользователь или ``None``.
        """
        stmt = select(User).where(User.telegram_id == telegram_id)
        if with_profile:
            stmt = stmt.options(selectinload(User.student_profile))
        return (await self._session.execute(stmt)).scalar_one_or_none()
