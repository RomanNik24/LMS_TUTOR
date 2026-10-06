"""Движок и сессии SQLAlchemy (задача T1.06, docs/03 §6).

Правила Unit of Work:
- сессия создаётся на запрос / событие бота / задачу воркера;
- **commit делает только сервисный слой**; здесь commit не вызывается;
- при исключении выполняется ``rollback`` и ошибка пробрасывается дальше.

Зависимость FastAPI ``get_session`` лежит в ``src/api/deps.py`` и использует
``session_scope``; бот и воркер используют ``session_scope`` напрямую.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(database_url: str) -> AsyncEngine:
    """Создать асинхронный движок (asyncpg) по строке подключения.

    Args:
        database_url: URL вида ``postgresql+asyncpg://...``.

    Returns:
        Асинхронный движок SQLAlchemy.
    """
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    """Создать фабрику сессий.

    ``expire_on_commit=False``: после ``commit`` в сервисе объекты остаются
    доступными без неявных обращений к БД (ленивая загрузка в async запрещена).

    Args:
        engine: Асинхронный движок.

    Returns:
        Фабрика ``AsyncSession``.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Выдать сессию на одну единицу работы (запрос, событие бота, задачу).

    Коммит здесь НЕ выполняется (его делает сервис). Если внутри блока
    возникло исключение, транзакция откатывается, исключение пробрасывается.

    Args:
        factory: Фабрика сессий.

    Yields:
        Открытая ``AsyncSession``.
    """
    async with factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
