"""``TelegramNotifier``: отправка уведомлений через Bot API (T5.02, docs/05 §6).

Бот приходит снаружи (его создаёт только ``src/bot/client.py``). Все ошибки библиотеки
переводятся в сигналы ``Notifier`` из слоя сервисов, чтобы вызывающий код не зависел от
транспорта. Текст отправляется без разметки: в нём бывают названия заданий и комментарии
пользователей, которые не должны превращаться в HTML.
"""

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.services.notifier import (
    MessageButton,
    NotifierBlockedError,
    NotifierPermanentError,
    NotifierTemporaryError,
    OutgoingMessage,
)


def _button(button: MessageButton) -> InlineKeyboardButton:
    if button.web_app:
        return InlineKeyboardButton(text=button.text, web_app=WebAppInfo(url=button.url))
    return InlineKeyboardButton(text=button.text, url=button.url)


def _markup(message: OutgoingMessage) -> InlineKeyboardMarkup | None:
    if not message.buttons:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button(button) for button in row] for row in message.buttons]
    )


class TelegramNotifier:
    """Реализация ``Notifier`` поверх ``aiogram.Bot``."""

    def __init__(self, bot: Bot) -> None:
        """Создать отправителя.

        Args:
            bot: Бот, созданный через ``build_bot``.
        """
        self._bot = bot

    async def send(self, telegram_id: int, message: OutgoingMessage) -> None:
        """Отправить сообщение, переведя ошибки Telegram в сигналы ``Notifier``."""
        try:
            await self._bot.send_message(
                chat_id=telegram_id,
                text=message.text,
                reply_markup=_markup(message),
                parse_mode=None,
            )
        except TelegramForbiddenError as error:
            raise NotifierBlockedError("Получатель заблокировал бота.") from error
        except TelegramRetryAfter as error:
            raise NotifierTemporaryError(
                "Telegram просит подождать.", retry_after=error.retry_after
            ) from error
        except (TelegramNetworkError, TelegramServerError) as error:
            raise NotifierTemporaryError("Сбой связи с Telegram.") from error
        except TelegramBadRequest as error:
            raise NotifierPermanentError("Telegram отклонил сообщение.") from error
        except TelegramAPIError as error:
            raise NotifierPermanentError("Telegram вернул ошибку.") from error
