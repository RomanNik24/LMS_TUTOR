"""Роутер ``/admin/staff*`` (docs/08 §5.3): сотрудники, только владелец."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from src.api.deps import OwnerActor, get_bot_username, get_staff_service
from src.api.v1.invitations import invitation_response
from src.api.v1.responses import error_responses
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.schemas.staff import StaffCreate, StaffItem, StaffListPage, StaffUpdate
from src.schemas.students import InvitationResponse
from src.services.staff import StaffService

router = APIRouter(prefix="/admin/staff", tags=["admin-staff"])

StaffId = Annotated[int, Path(ge=1)]
Service = Annotated[StaffService, Depends(get_staff_service)]


@router.get(
    "",
    response_model=StaffListPage,
    summary="Список сотрудников",
    operation_id="list_staff",
    responses=error_responses(401, 403, 422, 429),
)
async def list_staff(
    actor: OwnerActor,
    service: Service,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)] = LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StaffListPage:
    """Сотрудники по алфавиту имени; архивные — при ``include_archived=true``."""
    return await service.list_staff(
        actor, include_archived=include_archived, limit=limit, offset=offset
    )


@router.post(
    "",
    response_model=StaffItem,
    status_code=status.HTTP_201_CREATED,
    summary="Создать профиль сотрудника",
    operation_id="create_staff",
    responses=error_responses(401, 403, 422, 429),
)
async def create_staff(body: StaffCreate, actor: OwnerActor, service: Service) -> StaffItem:
    """Создать менеджера или владельца (Telegram привязывается по приглашению)."""
    return await service.create_staff(actor, body)


@router.patch(
    "/{staff_id}",
    response_model=StaffItem,
    summary="Изменить имя или роль сотрудника",
    operation_id="update_staff",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def update_staff(
    staff_id: StaffId, body: StaffUpdate, actor: OwnerActor, service: Service
) -> StaffItem:
    """Имя и/или роль; смена роли удаляет сессии, последнего владельца понизить нельзя."""
    return await service.update_staff(actor, staff_id, body)


@router.post(
    "/{staff_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать или перевыпустить приглашение сотрудника",
    operation_id="create_staff_invitation",
    responses=error_responses(400, 401, 403, 404, 429),
)
async def create_staff_invitation(
    staff_id: StaffId,
    actor: OwnerActor,
    service: Service,
    bot_username: Annotated[str, Depends(get_bot_username)],
) -> InvitationResponse:
    """Выпустить приглашение сотруднику; токен виден только в этом ответе."""
    issued = await service.invite_staff(actor, staff_id)
    return invitation_response(issued, bot_username)


@router.post(
    "/{staff_id}/archive",
    response_model=StaffItem,
    summary="Архивировать сотрудника",
    operation_id="archive_staff",
    responses=error_responses(400, 401, 403, 404, 429),
)
async def archive_staff(staff_id: StaffId, actor: OwnerActor, service: Service) -> StaffItem:
    """Архив: вход закрыт, сессии удалены; последнего владельца архивировать нельзя."""
    return await service.archive_staff(actor, staff_id)
