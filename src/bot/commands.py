"""Меню команд (``setMyCommands``) по состоянию пользователя (docs/05 §2)."""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

from src.core import texts
from src.core.enums import UserRole


def commands_for(role: UserRole | None) -> list[BotCommand]:
    """Список команд для гостя (``None``), ученика или персонала.

    Команда ``/hw`` появится вместе с ДЗ (этап 4).
    """
    start = BotCommand(command="start", description=texts.BOT_CMD_START)
    help_command = BotCommand(command="help", description=texts.BOT_CMD_HELP)
    if role is None:
        return [start, help_command]
    return [
        start,
        BotCommand(command="app", description=texts.BOT_CMD_APP),
        BotCommand(command="today", description=texts.BOT_CMD_TODAY),
        BotCommand(command="web", description=texts.BOT_CMD_WEB),
        BotCommand(command="logout", description=texts.BOT_CMD_LOGOUT),
        help_command,
    ]


async def set_commands(bot: Bot, chat_id: int, role: UserRole | None) -> None:
    """Выставить меню команд для конкретного чата (``BotCommandScopeChat``)."""
    await bot.set_my_commands(commands_for(role), scope=BotCommandScopeChat(chat_id=chat_id))
