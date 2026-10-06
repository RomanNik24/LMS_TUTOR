"""``ProfileService``: данные текущего пользователя (``GET/PATCH /me``, docs/08 §2)."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.exceptions import NotFoundError
from src.core.timeutils import utcnow
from src.db.models import User
from src.repositories.users import UserRepository


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
