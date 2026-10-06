"""Зависимости FastAPI (задача T1.06).

Здесь только ``get_session``; ``current_user`` и ``require_role`` появятся
в T1.08 вместе с сессиями Redis.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.db.session import SessionFactory, create_engine, create_session_factory, session_scope


@lru_cache(maxsize=1)
def get_session_factory() -> SessionFactory:
    """Вернуть единую фабрику сессий приложения (создаётся при первом обращении)."""
    settings = Settings()
    return create_session_factory(create_engine(settings.database_url))


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: сессия на запрос.

    Commit выполняет сервис; при исключении выполняется rollback
    (см. ``session_scope``).

    Yields:
        ``AsyncSession`` на время запроса.
    """
    async with session_scope(get_session_factory()) as session:
        yield session
