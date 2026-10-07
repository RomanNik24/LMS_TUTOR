"""Роутер ``/files*`` (docs/08 §6): подписанные ссылки на файлы.

Доступ у любого авторизованного пользователя, но права проверяет сервис: ученик получает
ссылки только на свои файлы и материалы своих заданий, чужое — 404.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from src.api.deps import current_user, get_file_service
from src.api.v1.responses import error_responses
from src.core.current_user import CurrentUser
from src.schemas.files import FileUrl
from src.services.files import FileService

router = APIRouter(prefix="/files", tags=["files"])

Actor = Annotated[CurrentUser, Depends(current_user)]
Service = Annotated[FileService, Depends(get_file_service)]


@router.get(
    "/{file_id}/url",
    response_model=FileUrl,
    summary="Ссылка на файл выдачи",
    operation_id="get_file_url",
    responses=error_responses(401, 404, 429),
)
async def get_file_url(
    file_id: Annotated[int, Path(ge=1)], actor: Actor, service: Service
) -> FileUrl:
    """Подписанная ссылка на файл решения или проверки; живёт 10 минут."""
    return await service.file_url(actor, file_id)


@router.get(
    "/materials/{material_id}/url",
    response_model=FileUrl,
    summary="Ссылка на материал задания",
    operation_id="get_material_url",
    responses=error_responses(401, 404, 429),
)
async def get_material_url(
    material_id: Annotated[int, Path(ge=1)], actor: Actor, service: Service
) -> FileUrl:
    """Подписанная ссылка на материал задания; живёт 10 минут."""
    return await service.material_url(actor, material_id)
