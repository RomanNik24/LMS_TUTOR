"""Middleware бота (docs/05 §1, docs/03 §6).

``DbSessionMiddleware`` — сессия БД и ``AuthService`` на каждый апдейт.
``AuthMiddleware`` — определяет пользователя по ``telegram_id`` и кладёт в данные
хэндлера ``current_user`` (``CurrentUser`` либо ``None`` для гостя), ``display_name``
и ``access_closed`` (архивный пользователь обрабатывается как гость).
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TelegramUser
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.current_user import CurrentUser
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.repositories.users import UserRepository
from src.services.auth import AuthService

SessionScope = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """Открывает сессию БД на апдейт и создаёт ``AuthService``."""

    def __init__(self, scope: SessionScope, redis: Redis, bot_token: str) -> None:
        """Сохранить зависимости.

        Args:
            scope: Фабрика контекста сессии (``session_scope`` или подмена в тестах).
            redis: Клиент Redis.
            bot_token: Токен бота (для ``AuthService``).
        """
        self._scope = scope
        self._redis = redis
        self._bot_token = bot_token

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        """Выполнить хэндлер внутри единицы работы."""
        async with self._scope() as session:
            data["session"] = session
            data["auth"] = AuthService(
                session, SessionStore(self._redis), RateLimiter(self._redis), self._bot_token
            )
            return await handler(event, data)


class AuthMiddleware(BaseMiddleware):
    """Определяет пользователя по ``telegram_id`` (гость → ``current_user=None``)."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        """Заполнить ``current_user``, ``display_name`` и ``access_closed``."""
        session: AsyncSession = data["session"]
        telegram_user: TelegramUser | None = data.get("event_from_user")
        current_user: CurrentUser | None = None
        display_name: str | None = None
        access_closed = False
        if telegram_user is not None:
            user = await UserRepository(session).get_by_telegram_id(telegram_user.id)
            if user is not None and user.is_active:
                current_user = CurrentUser(id=user.id, role=user.role, timezone=user.timezone)
                display_name = user.display_name
            elif user is not None:
                access_closed = True
        data["current_user"] = current_user
        data["display_name"] = display_name
        data["access_closed"] = access_closed
        return await handler(event, data)
