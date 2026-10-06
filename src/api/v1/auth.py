"""Роутер ``/auth/*`` (docs/08 §2): вход через Telegram и по ссылке, выход.

Роутеры тонкие: разбор запроса → вызов сервиса → ответ. На весь роутер
действует лимит 10 запросов в минуту на IP (docs/08 §10).
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from src.api.cookies import clear_session_cookie, set_session_cookie
from src.api.deps import (
    current_user,
    get_auth_service,
    get_profile_service,
    get_session_store,
    rate_limit_auth,
)
from src.api.v1.responses import error_responses
from src.core.config import get_settings
from src.core.constants import SESSION_COOKIE_NAME
from src.core.current_user import CurrentUser
from src.core.session_store import SessionStore
from src.schemas.auth import LinkLoginRequest, MeResponse, TelegramLoginRequest
from src.services.auth import AuthService
from src.services.profile import ProfileService

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(rate_limit_auth)])


async def _login(
    user: CurrentUser,
    auth: AuthService,
    profiles: ProfileService,
    response: Response,
) -> MeResponse:
    """Создать сессию, поставить cookie и вернуть ``Me``."""
    session_id, ttl = await auth.create_session(user)
    set_session_cookie(response, session_id, ttl, secure=get_settings().session_cookie_secure)
    return MeResponse.model_validate(await profiles.get_me(user))


@router.post(
    "/telegram",
    response_model=MeResponse,
    summary="Вход через Telegram Mini App (initData)",
    operation_id="auth_telegram_login",
    responses=error_responses(401, 422, 429),
)
async def telegram_login(
    body: TelegramLoginRequest,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    profiles: Annotated[ProfileService, Depends(get_profile_service)],
) -> MeResponse:
    """Проверить подпись и срок ``initData`` (≤ 24 ч), создать сессию, поставить cookie."""
    user = await auth.authenticate_telegram(body.init_data)
    return await _login(user, auth, profiles, response)


@router.post(
    "/link",
    response_model=MeResponse,
    summary="Вход по одноразовой ссылке из бота (/web)",
    operation_id="auth_link_login",
    responses=error_responses(404, 409, 422, 429),
)
async def link_login(
    body: LinkLoginRequest,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    profiles: Annotated[ProfileService, Depends(get_profile_service)],
) -> MeResponse:
    """Погасить ссылку входа (только POST, одноразово), создать сессию, поставить cookie."""
    user = await auth.consume_web_login(body.token)
    return await _login(user, auth, profiles, response)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход: удалить текущую сессию",
    operation_id="auth_logout",
    responses=error_responses(401, 429),
)
async def logout(
    response: Response,
    _user: Annotated[CurrentUser, Depends(current_user)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    """Удалить сессию на сервере и очистить cookie."""
    if session_id:
        await store.delete(session_id)
    clear_session_cookie(response, secure=get_settings().session_cookie_secure)
