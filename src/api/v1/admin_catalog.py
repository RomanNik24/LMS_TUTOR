"""Каталог услуг: ``/admin/catalog`` (docs/08 §5.7, персонал) и ``GET /catalog`` (§3).

``GET /catalog`` доступен любому вошедшему пользователю.

Гостям и ученикам отдаются только опубликованные карточки без служебных полей.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from src.api.deps import StaffActor, current_user, get_catalog_service
from src.api.v1.responses import error_responses
from src.core.current_user import CurrentUser
from src.schemas.catalog import (
    CatalogCreate,
    CatalogItemAdmin,
    CatalogItemPublic,
    CatalogReorder,
    CatalogUpdate,
)
from src.services.catalog import CatalogService

admin_router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"])
public_router = APIRouter(prefix="/catalog", tags=["catalog"])

Catalog = Annotated[CatalogService, Depends(get_catalog_service)]
ItemId = Annotated[int, Path(ge=1)]


@public_router.get(
    "",
    response_model=list[CatalogItemPublic],
    summary="Каталог услуг",
    operation_id="list_published_catalog",
    responses=error_responses(401, 429),
)
async def list_published_catalog(
    user: Annotated[CurrentUser, Depends(current_user)], service: Catalog
) -> list[CatalogItemPublic]:
    """Опубликованные карточки по порядку."""
    del user  # нужен только вход
    return await service.list_published()


@admin_router.get(
    "",
    response_model=list[CatalogItemAdmin],
    summary="Все карточки каталога",
    operation_id="list_catalog",
    responses=error_responses(401, 403, 429),
)
async def list_catalog(actor: StaffActor, service: Catalog) -> list[CatalogItemAdmin]:
    """Все карточки, включая неопубликованные, по порядку показа."""
    return await service.list_all(actor)


@admin_router.post(
    "",
    response_model=CatalogItemAdmin,
    status_code=status.HTTP_201_CREATED,
    summary="Создать карточку",
    operation_id="create_catalog_item",
    responses=error_responses(401, 403, 422, 429),
)
async def create_catalog_item(
    body: CatalogCreate, actor: StaffActor, service: Catalog
) -> CatalogItemAdmin:
    """Новая карточка встаёт в конец списка; по умолчанию не опубликована."""
    return await service.create(actor, body)


@admin_router.put(
    "/order",
    response_model=list[CatalogItemAdmin],
    summary="Задать порядок карточек",
    operation_id="reorder_catalog",
    responses=error_responses(401, 403, 422, 429),
)
async def reorder_catalog(
    body: CatalogReorder, actor: StaffActor, service: Catalog
) -> list[CatalogItemAdmin]:
    """Тело — идентификаторы всех карточек в новом порядке сверху вниз."""
    return await service.reorder(actor, body)


@admin_router.patch(
    "/{item_id}",
    response_model=CatalogItemAdmin,
    summary="Изменить карточку",
    operation_id="update_catalog_item",
    responses=error_responses(401, 403, 404, 422, 429),
)
async def update_catalog_item(
    item_id: ItemId, body: CatalogUpdate, actor: StaffActor, service: Catalog
) -> CatalogItemAdmin:
    """Поля карточки, порядок (`sort_order`) и публикация."""
    return await service.update(actor, item_id, body)


@admin_router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить карточку",
    operation_id="delete_catalog_item",
    responses=error_responses(401, 403, 404, 429),
)
async def delete_catalog_item(item_id: ItemId, actor: StaffActor, service: Catalog) -> Response:
    """Удаляет карточку насовсем."""
    await service.delete(actor, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
