"""``ProfileService``: данные текущего пользователя (``GET/PATCH /me``, docs/08 §2)."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.exceptions import NotFoundError
from src.core.timeutils import utcnow
from src.db.models import User
from src.repositories.users import UserRepository


@dataclass(frozen=True)
class Account:
    """Снимок учётной записи для определения доступа (сессия API, апдейт бота).

    Attributes:
        user: Идентификатор, роль и часовой пояс.
        display_name: Имя для обращения.
        is_active: ``False`` — пользователь в архиве.
    """

    user: CurrentUser
    display_name: str
    is_active: bool


def _account_of(user: User) -> Account:
    return Account(
        user=CurrentUser(id=user.id, role=user.role, timezone=user.timezone),
        display_name=user.display_name,
        is_active=user.is_active,
    )


class ProfileService:
    """Чтение и изменение собственного профиля."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохранить сессию БД."""
        self._session = session
        self._users = UserRepository(session)

    async def get_me(self, actor: CurrentUser) -> User:
        """Вернуть запись текущего пользователя.

        Raises:
            NotFoundError: Пользователь удалён.
        """
        user = await self._users.get_by_id(actor.id)
        if user is None:
            raise NotFoundError(texts.USER_NOT_FOUND)
        return user

    async def update_me(
        self, actor: CurrentUser, *, timezone: str | None, display_name: str | None
    ) -> User:
        """Изменить ``timezone`` и/или ``display_name`` (роль и прочее менять нельзя).

        Args:
            actor: Текущий пользователь.
            timezone: Новый IANA-пояс (уже проверен схемой) или ``None``.
            display_name: Новое имя или ``None``.

        Returns:
            Обновлённый пользователь.
        """
        user = await self.get_me(actor)
        if timezone is not None:
            user.timezone = timezone
        if display_name is not None:
            user.display_name = display_name
        user.updated_at = utcnow()
        await self._session.commit()
        return user

    async def find_account(self, user_id: int) -> Account | None:
        """Найти учётную запись по ``users.id`` (``None`` — пользователя нет)."""
        user = await self._users.get_by_id(user_id)
        return None if user is None else _account_of(user)

    async def find_account_by_telegram_id(self, telegram_id: int) -> Account | None:
        """Найти учётную запись по Telegram ID (``None`` — гость)."""
        user = await self._users.get_by_telegram_id(telegram_id)
        return None if user is None else _account_of(user)

    async def set_bot_blocked(self, telegram_id: int, blocked: bool) -> None:
        """Отметить, что пользователь заблокировал (или вернул) бота (``my_chat_member``)."""
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            return
        user.bot_blocked = blocked
        user.updated_at = utcnow()
        await self._session.commit()
