"""Репозиторий пользователей (задача T1.06, docs/04 §2.1, docs/08 §2)."""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.enums import UserRole
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

    async def get_first_by_role(self, role: UserRole) -> User | None:
        """Вернуть любого пользователя с ролью (например, проверить наличие владельца).

        Args:
            role: Роль.

        Returns:
            Пользователь с наименьшим id или ``None``.
        """
        stmt = select(User).where(User.role == role).order_by(User.id).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def lock_active_owner_ids(self) -> list[int]:
        """Заблокировать (``FOR UPDATE``) и вернуть id активных владельцев.

        Блокировка нужна, чтобы два одновременных понижения или архивации не оставили систему
        без владельца: второй запрос дождётся первого и увидит уже одного владельца.
        """
        stmt = (
            select(User.id)
            .where(User.role == UserRole.OWNER, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_staff(self, *, include_archived: bool) -> list[User]:
        """Сотрудники (owner и manager) по алфавиту имени.

        Args:
            include_archived: Включать ли архивных.
        """
        stmt = select(User).where(User.role.in_([UserRole.OWNER, UserRole.MANAGER]))
        if not include_archived:
            stmt = stmt.where(User.is_active.is_(True))
        stmt = stmt.order_by(User.display_name, User.id)
        return list((await self._session.execute(stmt)).scalars())

    async def list_by_ids(self, user_ids: Collection[int]) -> list[User]:
        """Пользователи по списку id (любые роли и состояния), по возрастанию id."""
        if not user_ids:
            return []
        stmt = select(User).where(User.id.in_(list(user_ids))).order_by(User.id)
        return list((await self._session.execute(stmt)).scalars())
