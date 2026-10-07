"""TelegramNotifier: перевод ошибок Bot API в сигналы Notifier (T5.02)."""

from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramConflictError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup
from src.bot.notifier import TelegramNotifier
from src.services.notifier import (
    MessageButton,
    NotifierBlockedError,
    NotifierPermanentError,
    NotifierTemporaryError,
    OutgoingMessage,
)

METHOD = SendMessage(chat_id=1, text="x")
MESSAGE = OutgoingMessage(text="Привет")


def notifier_with(side_effect: Exception | None = None) -> tuple[TelegramNotifier, AsyncMock]:
    bot = AsyncMock(spec=Bot)
    if side_effect is not None:
        bot.send_message.side_effect = side_effect
    return TelegramNotifier(bot), bot.send_message


async def test_sends_plain_text_without_markup() -> None:
    notifier, send = notifier_with()
    await notifier.send(42, MESSAGE)
    send.assert_awaited_once_with(chat_id=42, text="Привет", reply_markup=None, parse_mode=None)


async def test_buttons_become_inline_keyboard_with_url_and_web_app() -> None:
    notifier, send = notifier_with()
    message = OutgoingMessage(
        text="ДЗ",
        buttons=(
            (MessageButton("Телемост", "https://telemost.example/x"),),
            (MessageButton("Открыть ДЗ", "https://lms.example/app/homework/1", web_app=True),),
        ),
    )
    await notifier.send(7, message)
    markup = send.await_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    first, second = markup.inline_keyboard
    assert first[0].url == "https://telemost.example/x"
    assert first[0].web_app is None
    assert second[0].web_app is not None
    assert second[0].web_app.url == "https://lms.example/app/homework/1"


async def test_forbidden_means_blocked() -> None:
    notifier, _ = notifier_with(TelegramForbiddenError(METHOD, "Forbidden: bot was blocked"))
    with pytest.raises(NotifierBlockedError):
        await notifier.send(1, MESSAGE)


async def test_retry_after_is_temporary_and_keeps_requested_pause() -> None:
    notifier, _ = notifier_with(TelegramRetryAfter(METHOD, "Too Many Requests", 30))
    with pytest.raises(NotifierTemporaryError) as caught:
        await notifier.send(1, MESSAGE)
    assert caught.value.retry_after == 30


@pytest.mark.parametrize(
    "error",
    [TelegramNetworkError(METHOD, "timeout"), TelegramServerError(METHOD, "Bad Gateway")],
)
async def test_network_and_server_errors_are_temporary(error: Exception) -> None:
    notifier, _ = notifier_with(error)
    with pytest.raises(NotifierTemporaryError) as caught:
        await notifier.send(1, MESSAGE)
    assert caught.value.retry_after is None


@pytest.mark.parametrize(
    "error",
    [TelegramBadRequest(METHOD, "chat not found"), TelegramConflictError(METHOD, "conflict")],
)
async def test_other_api_errors_are_permanent(error: Exception) -> None:
    notifier, _ = notifier_with(error)
    with pytest.raises(NotifierPermanentError):
        await notifier.send(1, MESSAGE)
