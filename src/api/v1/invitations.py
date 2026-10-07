"""Общее для приглашений в админке: ссылка из токена и отзыв (docs/08 §5.2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from src.api.deps import StaffActor, get_auth_service
from src.api.v1.responses import error_responses
from src.core.constants import BOT_INVITE_PAYLOAD_PREFIX
from src.schemas.students import InvitationResponse
from src.services.auth import AuthService, IssuedToken

router = APIRouter(prefix="/admin", tags=["admin-invitations"])


def invitation_response(issued: IssuedToken, bot_username: str) -> InvitationResponse:
    """Ответ с готовой ссылкой ``https://t.me/<bot>?start=inv_<token>`` (токен виден один раз)."""
    url = f"https://t.me/{bot_username}?start={BOT_INVITE_PAYLOAD_PREFIX}{issued.token}"
    return InvitationResponse(id=issued.id, url=url, expires_at=issued.expires_at)


@router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отозвать приглашение",
    operation_id="revoke_invitation",
    responses=error_responses(401, 403, 404, 429),
)
async def revoke_invitation(
    invitation_id: Annotated[int, Path(ge=1)],
    actor: StaffActor,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    """Отозвать действующее приглашение (сотрудника — только владелец)."""
    await auth.revoke_invitation(actor, invitation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
