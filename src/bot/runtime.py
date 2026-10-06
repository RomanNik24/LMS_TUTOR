"""Запуск бота внутри приложения: polling или webhook (docs/05 §7, docs/03 §12).

Без ``BOT_TOKEN`` бот не создаётся, приложение стартует без него.
Webhook: URL = ``WEBHOOK_URL`` + секретный сегмент, производный от
``WEBHOOK_SECRET``; Telegram дополнительно присылает секретный заголовок.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from redis.asyncio import Redis

from src.bot.client import build_bot
from src.bot.dispatcher import create_dispatcher
from src.bot.middlewares import SessionScope
from src.core.config import Settings
from src.core.constants import BOT_ALLOWED_UPDATES, BOT_MODE_WEBHOOK

logger = logging.getLogger(__name__)


def webhook_path_secret(webhook_secret: str) -> str:
    """Секретный сегмент пути вебхука (производный от ``WEBHOOK_SECRET``).

    Отдельная переменная окружения не нужна: сегмент нельзя восстановить из пути
    без знания секрета, а сам секрет в URL не светится.
    """
    return hashlib.sha256(f"webhook-path:{webhook_secret}".encode()).hexdigest()[:32]


def webhook_target_url(settings: Settings) -> str:
    """Полный URL, который регистрируется в Telegram (``WEBHOOK_URL`` + секретный сегмент)."""
    secret = webhook_path_secret(settings.webhook_secret.get_secret_value())
    return f"{settings.webhook_url.rstrip('/')}/{secret}"


@dataclass
class BotRuntime:
    """Запущенный бот: ``Bot``, ``Dispatcher`` и фоновая задача polling."""

    bot: Bot
    dispatcher: Dispatcher
    polling_task: asyncio.Task[None] | None = None

    async def stop(self) -> None:
        """Остановить polling и закрыть HTTP-сессию бота."""
        if self.polling_task is not None:
            self.polling_task.cancel()
            await asyncio.gather(self.polling_task, return_exceptions=True)
        await self.bot.session.close()


async def start_bot(settings: Settings, redis: Redis, scope: SessionScope) -> BotRuntime | None:
    """Создать и запустить бота; ``None``, если ``BOT_TOKEN`` не задан."""
    bot = build_bot(settings)
    if bot is None:
        logger.info("BOT_TOKEN не задан: приложение стартует без бота")
        return None
    dispatcher = create_dispatcher(settings, redis, scope)
    runtime = BotRuntime(bot=bot, dispatcher=dispatcher)
    allowed = list(BOT_ALLOWED_UPDATES)
    if settings.bot_mode == BOT_MODE_WEBHOOK:
        await bot.set_webhook(
            webhook_target_url(settings),
            secret_token=settings.webhook_secret.get_secret_value(),
            allowed_updates=allowed,
        )
        logger.info("Webhook бота зарегистрирован")
    else:
        await bot.delete_webhook()
        runtime.polling_task = asyncio.create_task(
            dispatcher.start_polling(bot, allowed_updates=allowed, handle_signals=False)
        )
        logger.info("Бот запущен в режиме polling")
    return runtime
