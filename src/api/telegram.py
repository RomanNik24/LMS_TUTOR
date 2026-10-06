"""Webhook Telegram: ``POST /telegram/webhook/{secret}`` (docs/05 §7, docs/08 §3).

Защита: секретный сегмент пути (производный от ``WEBHOOK_SECRET``) и заголовок
``X-Telegram-Bot-Api-Secret-Token``; обе проверки через ``hmac.compare_digest``.
CSRF-проверка для ``/telegram/*`` отключена (``CSRF_EXEMPT_PATH_PREFIXES``).
Эндпоинт не входит в OpenAPI: фронтенд его не использует.
"""

import hmac

from aiogram.types import Update
from fastapi import APIRouter, Request

from src.bot.runtime import BotRuntime, webhook_path_secret
from src.core.config import get_settings
from src.core.constants import BOT_WEBHOOK_AUTH_HEADER, BOT_WEBHOOK_PATH
from src.core.exceptions import NotFoundError, PermissionDeniedError

router = APIRouter()


def _equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


@router.post(
    BOT_WEBHOOK_PATH + "/{path_secret}",
    include_in_schema=False,
    summary="Webhook Telegram",
    operation_id="telegram_webhook",
)
async def telegram_webhook(path_secret: str, request: Request) -> dict[str, bool]:
    """Принять апдейт от Telegram и передать его диспетчеру бота."""
    runtime: BotRuntime | None = getattr(request.app.state, "bot_runtime", None)
    settings = get_settings()
    secret = settings.webhook_secret.get_secret_value()
    # Без бота или секрета эндпоинт «не существует»; неверный путь тоже даёт 404.
    if runtime is None or not secret or not _equal(path_secret, webhook_path_secret(secret)):
        raise NotFoundError()
    header = request.headers.get(BOT_WEBHOOK_AUTH_HEADER, "")
    if not _equal(header, secret):
        raise PermissionDeniedError()
    update = Update.model_validate(await request.json(), context={"bot": runtime.bot})
    await runtime.dispatcher.feed_update(runtime.bot, update)
    return {"ok": True}
