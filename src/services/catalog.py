"""``CatalogService``: каталог услуг (docs/08 §3 и §5.7, docs/04 §1.4).

Управляет карточками только персонал; гостям и ученикам отдаются опубликованные карточки по
порядку. ``list_published`` не требует пользователя: каталог показывается и гостю в боте.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.db.models import CatalogItem
from src.repositories.catalog import CatalogRepository
from src.schemas.catalog import (
    CatalogCreate,
    CatalogItemAdmin,
    CatalogItemPublic,
    CatalogReorder,
    CatalogUpdate,
)
from src.services.auth import STAFF_ROLES


class CatalogService:
    """Чтение витрины и управление карточками."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис на сессию текущей единицы работы."""
        self._session = session
        self._items = CatalogRepository(session)

    async def list_published(self) -> list[CatalogItemPublic]:
        """Опубликованные карточки по порядку (публичные данные)."""
        return [CatalogItemPublic.model_validate(i) for i in await self._items.list_published()]

    async def list_all(self, actor: CurrentUser) -> list[CatalogItemAdmin]:
        """Все карточки для персонала.

        Raises:
            PermissionDeniedError: Не сотрудник.
        """
        self._require_staff(actor)
        return [CatalogItemAdmin.model_validate(i) for i in await self._items.list_all()]

    async def create(self, actor: CurrentUser, data: CatalogCreate) -> CatalogItemAdmin:
        """Создать карточку в конце списка.

        Raises:
            PermissionDeniedError: Не сотрудник.
        """
        self._require_staff(actor)
        item = await self._items.add(
            CatalogItem(
                title=data.title,
                description=data.description,
                price_text=data.price_text,
                is_published=data.is_published,
                sort_order=await self._items.next_sort_order(),
            )
        )
        await self._session.commit()
        return CatalogItemAdmin.model_validate(item)

    async def update(
        self, actor: CurrentUser, item_id: int, data: CatalogUpdate
    ) -> CatalogItemAdmin:
        """Изменить поля карточки, порядок или публикацию.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``catalog_item_not_found``.
        """
        self._require_staff(actor)
        item = await self._get(item_id)
        for field in data.model_fields_set:
            setattr(item, field, getattr(data, field))
        await self._session.commit()
        return CatalogItemAdmin.model_validate(item)

    async def reorder(self, actor: CurrentUser, data: CatalogReorder) -> list[CatalogItemAdmin]:
        """Задать порядок: ``ids`` — все карточки сверху вниз.

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: ``catalog_reorder_invalid`` — список не совпадает с набором карточек.
        """
        self._require_staff(actor)
        items = {item.id: item for item in await self._items.list_all()}
        if set(data.ids) != set(items):
            raise ValidationError(texts.CATALOG_REORDER_INVALID, code="catalog_reorder_invalid")
        for position, item_id in enumerate(data.ids):
            items[item_id].sort_order = position
        await self._session.commit()
        return [CatalogItemAdmin.model_validate(items[item_id]) for item_id in data.ids]

    async def delete(self, actor: CurrentUser, item_id: int) -> None:
        """Удалить карточку.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``catalog_item_not_found``.
        """
        self._require_staff(actor)
        await self._items.delete(await self._get(item_id))
        await self._session.commit()

    # ------------------------------------------------------------------ внутреннее

    async def _get(self, item_id: int) -> CatalogItem:
        item = await self._items.get_by_id(item_id)
        if item is None:
            raise NotFoundError(texts.CATALOG_ITEM_NOT_FOUND, code="catalog_item_not_found")
        return item

    @staticmethod
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
