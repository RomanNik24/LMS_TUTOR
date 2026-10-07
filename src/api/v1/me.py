"""Роутер ``/me`` (docs/08 §2): профиль текущего пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import current_user, get_profile_service
from src.api.v1.responses import error_responses
from src.core.current_user import CurrentUser
from src.schemas.auth import MeResponse, MeUpdateRequest
from src.services.profile import ProfileService

router = APIRouter(tags=["me"])


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Текущий пользователь",
    operation_id="get_me",
    responses=error_responses(401, 429),
)
async def get_me(
    user: Annotated[CurrentUser, Depends(current_user)],
    profiles: Annotated[ProfileService, Depends(get_profile_service)],
) -> MeResponse:
    """Вернуть id, роль, имя и часовой пояс текущего пользователя."""
    return MeResponse.model_validate(await profiles.get_me(user))


@router.patch(
    "/me",
    response_model=MeResponse,
    summary="Изменить часовой пояс или имя",
    operation_id="update_me",
    responses=error_responses(401, 403, 422, 429),
)
async def update_me(
    body: MeUpdateRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    profiles: Annotated[ProfileService, Depends(get_profile_service)],
) -> MeResponse:
    """Изменить ``timezone`` и/или ``display_name`` (остальное менять нельзя)."""
    updated = await profiles.update_me(user, timezone=body.timezone, display_name=body.display_name)
    return MeResponse.model_validate(updated)
