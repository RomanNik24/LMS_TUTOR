"""Архивный пользователь: на любое сообщение и кнопку — «Доступ закрыт» (T8.03, docs/05 §3).

Роутер стоит после ``/start`` (приветствие и приглашения обрабатывает он) и перед остальными
обработчиками: архивная учётная запись не получает ни расписания, ни каталога, ни ссылок входа.
"""

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message
from src.core import texts


class AccessClosed(Filter):
    """Пропускает событие, если Telegram-аккаунт привязан к архивной учётной записи."""

    async def __call__(self, event: Message | CallbackQuery, access_closed: bool = False) -> bool:
        """``access_closed`` выставляет ``AuthMiddleware``."""
        del event
        return access_closed


async def closed_message(message: Message) -> None:
    """Ответ архивному пользователю на сообщение."""
    await message.answer(texts.BOT_ACCESS_CLOSED)


async def closed_callback(callback: CallbackQuery) -> None:
    """Ответ архивному пользователю на нажатие кнопки."""
    await callback.answer(texts.BOT_ACCESS_CLOSED, show_alert=True)


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``)."""
    router = Router(name="closed")
    router.message.register(closed_message, AccessClosed())
    router.callback_query.register(closed_callback, AccessClosed())
    return router
