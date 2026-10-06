"""Клавиатуры бота (docs/05 §5)."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from src.core import texts
from src.core.enums import UserRole

CALLBACK_RELINK_YES = "relink:yes"
CALLBACK_RELINK_NO = "relink:no"
CALLBACK_LOGOUT_YES = "logout:yes"
CALLBACK_LOGOUT_NO = "logout:no"

STUDENT_APP_PATH = "/app/"
STAFF_APP_PATH = "/admin/"


def app_url(public_base_url: str, role: UserRole) -> str | None:
    """Адрес Mini App для роли или ``None``, если он не годится для Telegram.

    Telegram принимает ``web_app`` только по HTTPS (docs/05 §5.3).
    """
    base = public_base_url.strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    path = STUDENT_APP_PATH if role == UserRole.STUDENT else STAFF_APP_PATH
    return base + path


def main_menu(role: UserRole | None, public_base_url: str) -> ReplyKeyboardMarkup:
    """Главное меню (ReplyKeyboard, постоянное) по состоянию пользователя.

    Кнопка «Открыть приложение» здесь ОБЫЧНАЯ текстовая, а не ``web_app``: Telegram не
    передаёт ``initData`` Mini App, открытым кнопкой клавиатуры (только инлайн-кнопкой,
    кнопкой меню и т. п.), и вход в приложение не сработал бы. По нажатию бот присылает
    инлайн-кнопку ``web_app`` (см. ``open_app_button``).
    """
    del public_base_url  # адрес нужен только инлайн-кнопке
    if role is None:
        rows = [
            [KeyboardButton(text=texts.BOT_BUTTON_CATALOG)],
            [KeyboardButton(text=texts.BOT_BUTTON_CONTACT)],
        ]
    else:
        label = texts.BOT_OPEN_APP_STUDENT if role == UserRole.STUDENT else texts.BOT_OPEN_APP_STAFF
        rows = [[KeyboardButton(text=label)]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def open_app_button(role: UserRole, public_base_url: str) -> InlineKeyboardMarkup | None:
    """Инлайн-кнопка ``web_app`` для ``/app``; ``None``, если адрес недоступен."""
    url = app_url(public_base_url, role)
    if url is None:
        return None
    label = texts.BOT_OPEN_APP_STUDENT if role == UserRole.STUDENT else texts.BOT_OPEN_APP_STAFF
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
    )


def relink_confirm() -> InlineKeyboardMarkup:
    """Кнопки подтверждения перепривязки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BOT_RELINK_YES, callback_data=CALLBACK_RELINK_YES)],
            [InlineKeyboardButton(text=texts.BOT_RELINK_CANCEL, callback_data=CALLBACK_RELINK_NO)],
        ]
    )


def logout_confirm() -> InlineKeyboardMarkup:
    """Кнопки подтверждения выхода."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BOT_LOGOUT_YES, callback_data=CALLBACK_LOGOUT_YES)],
            [InlineKeyboardButton(text=texts.BOT_RELINK_CANCEL, callback_data=CALLBACK_LOGOUT_NO)],
        ]
    )


def contact_button(url: str) -> InlineKeyboardMarkup:
    """URL-кнопка «Написать преподавателю»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BOT_CONTACT_LINK, url=url)]]
    )
