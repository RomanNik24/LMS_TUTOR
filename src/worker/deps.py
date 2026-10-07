"""Зависимости задач воркера: сессия БД на одну задачу (T5.04, docs/03 §6).

Правило Unit of Work: сессия создаётся на задачу, commit делает сервисный слой, при
исключении выполняется rollback.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import Context, TaskiqDepends

from src.db.session import SessionFactory, session_scope
from src.worker.broker import STATE_SESSION_FACTORY


async def get_session(context: Annotated[Context, TaskiqDepends()]) -> AsyncIterator[AsyncSession]:
    """Выдать сессию БД на время одной задачи."""
    factory: SessionFactory = context.state[STATE_SESSION_FACTORY]
    async with session_scope(factory) as session:
        yield session
