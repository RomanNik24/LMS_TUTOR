"""Меню команд (``setMyCommands``) по состоянию пользователя (docs/05 §2)."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat

from src.core import texts
from src.core.enums import UserRole

logger = logging.getLogger(__name__)


def commands_for(role: UserRole | None) -> list[BotCommand]:
    """Список команд для гостя (``None``), ученика или персонала."""
    start = BotCommand(command="start", description=texts.BOT_CMD_START)
    help_command = BotCommand(command="help", description=texts.BOT_CMD_HELP)
    if role is None:
        return [start, help_command]
    return [
        start,
        BotCommand(command="app", description=texts.BOT_CMD_APP),
        BotCommand(command="today", description=texts.BOT_CMD_TODAY),
        BotCommand(
            command="hw",
            description=(
                texts.BOT_CMD_HW_STUDENT if role == UserRole.STUDENT else texts.BOT_CMD_HW_STAFF
            ),
        ),
        BotCommand(command="web", description=texts.BOT_CMD_WEB),
        BotCommand(command="logout", description=texts.BOT_CMD_LOGOUT),
        help_command,
    ]


async def set_default_commands(bot: Bot) -> None:
    """Команды по умолчанию (для гостя) — для чатов, где ещё не выставлено своё меню.

    Сбой Telegram не мешает запуску бота: меню обновится при следующем ``/start``.
    """
    try:
        await bot.set_my_commands(commands_for(None))
    except TelegramAPIError:
        logger.warning("Failed to set default bot commands", exc_info=True)


async def set_commands(bot: Bot, chat_id: int, role: UserRole | None) -> None:
    """Выставить меню команд для конкретного чата (``BotCommandScopeChat``)."""
    await bot.set_my_commands(commands_for(role), scope=BotCommandScopeChat(chat_id=chat_id))
