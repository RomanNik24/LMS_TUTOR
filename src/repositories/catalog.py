"""Репозиторий каталога услуг (docs/04 §1.4)."""

from sqlalchemy import func, select

from src.db.models import CatalogItem
from src.repositories.base import BaseRepository


class CatalogRepository(BaseRepository[CatalogItem]):
    """Доступ к таблице ``catalog_items``."""

    async def get_by_id(self, item_id: int) -> CatalogItem | None:
        """Карточка по идентификатору."""
        return await self._session.get(CatalogItem, item_id)

    async def list_all(self) -> list[CatalogItem]:
        """Все карточки (и неопубликованные) в порядке показа."""
        stmt = select(CatalogItem).order_by(CatalogItem.sort_order, CatalogItem.id)
        return list((await self._session.execute(stmt)).scalars())

    async def list_published(self) -> list[CatalogItem]:
        """Опубликованные карточки в порядке показа."""
        stmt = (
            select(CatalogItem)
            .where(CatalogItem.is_published.is_(True))
            .order_by(CatalogItem.sort_order, CatalogItem.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def next_sort_order(self) -> int:
        """Порядок для новой карточки: после последней."""
        top = (await self._session.execute(select(func.max(CatalogItem.sort_order)))).scalar_one()
        return 0 if top is None else top + 1

    async def delete(self, item: CatalogItem) -> None:
        """Удалить карточку."""
        await self._session.delete(item)
        await self._session.flush()
