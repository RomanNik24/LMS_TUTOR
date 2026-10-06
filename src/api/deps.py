"""Зависимости FastAPI (задача T1.06).

``get_session`` (T1.06), ``get_redis``/``get_session_store``/``current_user``/
``require_role`` (T1.08). Права проверяет сервер: роль и активность берутся
из БД на каждом запросе, а не из cookie.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Cookie, Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import get_settings
from src.core.constants import (
    RATE_LIMIT_AUTH_PER_MINUTE,
    RATE_LIMIT_USER_PER_MINUTE,
    SESSION_COOKIE_NAME,
)
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import AppError, PermissionDeniedError
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.session import SessionFactory, create_engine, create_session_factory, session_scope
from src.repositories.users import UserRepository


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Вернуть единый движок БД приложения (создаётся при первом обращении)."""
    return create_engine(get_settings().database_url)


@lru_cache(maxsize=1)
def get_session_factory() -> SessionFactory:
    """Вернуть единую фабрику сессий приложения."""
    return create_session_factory(get_engine())


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: сессия на запрос.

    Commit выполняет сервис; при исключении выполняется rollback
    (см. ``session_scope``).

    Yields:
        ``AsyncSession`` на время запроса.
    """
    async with session_scope(get_session_factory()) as session:
        yield session


def _unauthenticated() -> AppError:
    """401 ``unauthenticated`` (docs/08 §1): нет или истекла сессия."""
    return AppError("Требуется вход.", code="unauthenticated", http_status=401)


def get_redis(request: Request) -> Redis:
    """Вернуть клиент Redis, созданный в lifespan приложения (``app.state.redis``)."""
    redis: Redis = request.app.state.redis
    return redis


def get_session_store(redis: Annotated[Redis, Depends(get_redis)]) -> SessionStore:
    """Вернуть хранилище сессий."""
    return SessionStore(redis)


async def rate_limit_auth(request: Request, redis: Annotated[Redis, Depends(get_redis)]) -> None:
    """Лимит ``/auth/*``: 10 запросов в минуту на IP (docs/08 §10).

    Подключается к роутеру ``/auth``. За Nginx реальный IP берётся из
    ``X-Forwarded-For`` — для этого uvicorn запускается с ``--proxy-headers``.
    """
    ip = request.client.host if request.client else "unknown"
    await RateLimiter(redis).hit("auth", ip, RATE_LIMIT_AUTH_PER_MINUTE)


async def current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> CurrentUser:
    """Определить текущего пользователя: cookie → Redis → пользователь из БД.

    Сессия продлевается (скользящий TTL). Архивный пользователь не проходит;
    его сессии при этом удаляются.

    Args:
        session: Сессия БД на запрос.
        store: Хранилище сессий.
        session_id: Идентификатор сессии из cookie.

    Returns:
        Снимок пользователя (id, роль, часовой пояс).

    Raises:
        AppError: 401 ``unauthenticated`` — нет cookie, сессия истекла,
            пользователь не найден или архивирован; 429 ``rate_limited`` —
            больше 120 запросов в минуту от пользователя.
    """
    if not session_id:
        raise _unauthenticated()
    data = await store.get(session_id)
    if data is None:
        raise _unauthenticated()
    user = await UserRepository(session).get_by_id(data.user_id)
    if user is None:
        await store.delete(session_id)
        raise _unauthenticated()
    if not user.is_active:
        await store.delete_all_for_user(user.id)
        raise _unauthenticated()
    await RateLimiter(redis).hit("user", str(user.id), RATE_LIMIT_USER_PER_MINUTE)
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


def require_role(*roles: UserRole) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Создать зависимость, пропускающую только указанные роли.

    Args:
        roles: Допустимые роли.

    Returns:
        Зависимость FastAPI: возвращает ``CurrentUser`` либо 403 ``permission_denied``.
    """
    allowed = frozenset(roles)

    async def _checker(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
        if user.role not in allowed:
            raise PermissionDeniedError()
        return user

    return _checker
