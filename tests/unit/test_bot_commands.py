"""Меню команд бота (T8.03): наборы для гостя, ученика и персонала, команды по умолчанию."""

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import TelegramMethod
from src.bot.commands import commands_for, set_default_commands
from src.core import texts
from src.core.enums import UserRole
from tests.integration.conftest import BOT_TOKEN, FakeTelegramSession


def names(role: UserRole | None) -> list[str]:
    return [command.command for command in commands_for(role)]


def test_guest_gets_only_start_and_help() -> None:
    assert names(None) == ["start", "help"]


def test_student_and_staff_get_full_menu_with_own_hw_description() -> None:
    expected = ["start", "app", "today", "hw", "web", "logout", "help"]
    assert names(UserRole.STUDENT) == expected
    assert names(UserRole.OWNER) == expected
    assert names(UserRole.MANAGER) == expected
    hw = {role: commands_for(role)[3].description for role in (UserRole.STUDENT, UserRole.OWNER)}
    assert hw[UserRole.STUDENT] == texts.BOT_CMD_HW_STUDENT
    assert hw[UserRole.OWNER] == texts.BOT_CMD_HW_STAFF


class FailingSession(FakeTelegramSession):
    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 - сигнатура задана aiogram
    ) -> Any:
        raise TelegramAPIError(method=method, message="boom")


async def test_default_commands_are_guest_commands() -> None:
    session = FakeTelegramSession()

    await set_default_commands(Bot(token=BOT_TOKEN, session=session))

    (call,) = session.of("SetMyCommands")
    assert [command.command for command in call.commands] == ["start", "help"]


async def test_telegram_failure_does_not_stop_startup() -> None:
    await set_default_commands(Bot(token=BOT_TOKEN, session=FailingSession()))
