"""Инициализация Sentry без персональных данных (задача T1.08, ADR 0005).

Sentry включается только при непустом ``SENTRY_DSN`` и не в ``local``.
``send_default_pii=False``; из событий удаляются тело запроса, cookie,
чувствительные заголовки и query-строка (в них бывают ``initData`` и токены).
"""

import logging

import sentry_sdk
from sentry_sdk.types import Event, Hint

from src.core.config import Settings
from src.core.constants import APP_ENV_LOCAL

logger = logging.getLogger(__name__)

_SENSITIVE_HEADERS = frozenset({"cookie", "authorization", "x-telegram-bot-api-secret-token"})


def scrub_event(event: Event, hint: Hint) -> Event | None:
    """Убрать из события Sentry всё, что может содержать секреты или ПДн.

    Args:
        event: Событие Sentry.
        hint: Служебная подсказка SDK (не используется).

    Returns:
        Очищенное событие.
    """
    del hint
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: value
                for key, value in headers.items()
                if key.lower() not in _SENSITIVE_HEADERS
            }
    event.pop("user", None)
    return event


def init_sentry(settings: Settings) -> bool:
    """Инициализировать Sentry, если это разрешено настройками.

    Args:
        settings: Настройки приложения.

    Returns:
        ``True``, если Sentry включён.
    """
    dsn = settings.sentry_dsn.get_secret_value().strip()
    if not dsn or settings.app_env == APP_ENV_LOCAL:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env,
        send_default_pii=False,
        before_send=scrub_event,
    )
    logger.info("Sentry включён")
    return True
