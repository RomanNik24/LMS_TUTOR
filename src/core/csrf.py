"""Защита от CSRF (задача T1.08, docs/09 §2.3.1, docs/08 §1).

Изменяющие запросы (``POST/PATCH/PUT/DELETE``) обязаны содержать заголовок
``X-Requested-With: XMLHttpRequest`` и ``Origin``, равный origin из
``PUBLIC_BASE_URL``; иначе 403. Webhook Telegram исключён (его защищает
секретный заголовок). Если ``PUBLIC_BASE_URL`` не задан — отказ (fail closed).
Реализован чистым ASGI-middleware, чтобы вернуть ошибку в едином формате.
"""

from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.constants import (
    CSRF_EXEMPT_PATH_PREFIXES,
    CSRF_REQUIRED_HEADER,
    CSRF_REQUIRED_HEADER_VALUE,
    CSRF_UNSAFE_METHODS,
)
from src.core.error_handlers import error_response
from src.core.logging import get_request_id

CSRF_REJECTED_MESSAGE = "Запрос отклонён."


def origin_of(url: str) -> str:
    """Вернуть origin (``scheme://host[:port]``) из URL; пустую строку, если URL пуст/неполон."""
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".lower()


class CsrfMiddleware:
    """ASGI-middleware проверки ``Origin`` и ``X-Requested-With``."""

    def __init__(self, app: ASGIApp, public_base_url: Callable[[], str]) -> None:
        """Создать middleware.

        Args:
            app: Следующее ASGI-приложение.
            public_base_url: Функция, возвращающая ``PUBLIC_BASE_URL`` (читается
                лениво, только для изменяющих запросов).
        """
        self._app = app
        self._public_base_url = public_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Пропустить безопасные/исключённые запросы, остальные проверить."""
        if (
            scope["type"] != "http"
            or scope["method"] not in CSRF_UNSAFE_METHODS
            or scope["path"].startswith(CSRF_EXEMPT_PATH_PREFIXES)
        ):
            await self._app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        reason = self._violation(headers)
        if reason is None:
            await self._app(scope, receive, send)
            return
        response = error_response(
            http_status=403,
            code="permission_denied",
            message=CSRF_REJECTED_MESSAGE,
            details={"reason": reason},
            request_id=get_request_id(Request(scope)),
        )
        await response(scope, receive, send)

    def _violation(self, headers: dict[str, str]) -> str | None:
        """Вернуть причину отказа или ``None``, если запрос допустим."""
        if headers.get(CSRF_REQUIRED_HEADER) != CSRF_REQUIRED_HEADER_VALUE:
            return "csrf_header"
        allowed = origin_of(self._public_base_url())
        if not allowed or origin_of(headers.get("origin", "")) != allowed:
            return "csrf_origin"
        return None
