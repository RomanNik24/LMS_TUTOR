"""Базовый репозиторий (задача T1.06, docs/03 §5–§6).

Репозиторий принимает ``AsyncSession`` и выполняет запросы к БД. Он делает
только ``flush`` (чтобы получить id и сработали ограничения БД); ``commit``
запрещён — его делает сервисный слой.
"""

from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):  # noqa: UP046 - явный Generic: проект на Python >= 3.11
    """Общая основа репозиториев сущностей."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохранить сессию.

        Args:
            session: Асинхронная сессия на текущую единицу работы.
        """
        self._session = session

    async def add(self, entity: ModelT) -> ModelT:
        """Добавить сущность в сессию и выполнить flush (без commit).

        Args:
            entity: Новая ORM-сущность.

        Returns:
            Та же сущность с заполненными серверными значениями (id и т. п.).
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def flush(self) -> None:
        """Отправить накопленные изменения в БД внутри текущей транзакции."""
        await self._session.flush()
