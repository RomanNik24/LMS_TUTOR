"""Единственная точка исходящих запросов к Telegram (docs/02 §6, задача T1.11).

Поддерживает ``TELEGRAM_API_BASE`` (альтернативный адрес Bot API) и
``TELEGRAM_PROXY_URL`` (HTTP-прокси; для SOCKS нужен пакет ``aiohttp-socks``).
Остальной код создаёт ``Bot`` только через ``build_bot``. Если ``BOT_TOKEN``
пуст, бота нет и приложение стартует без него.
"""

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import PRODUCTION, TelegramAPIServer

from src.core.config import Settings


def build_bot(settings: Settings) -> Bot | None:
    """Создать ``Bot`` из настроек.

    Args:
        settings: Настройки приложения.

    Returns:
        ``Bot`` либо ``None``, если ``BOT_TOKEN`` не задан.
    """
    token = settings.bot_token.get_secret_value().strip()
    if not token:
        return None
    api_base = settings.telegram_api_base.strip()
    api = TelegramAPIServer.from_base(api_base) if api_base else PRODUCTION
    proxy = settings.telegram_proxy_url.get_secret_value().strip() or None
    return Bot(token=token, session=AiohttpSession(api=api, proxy=proxy))
