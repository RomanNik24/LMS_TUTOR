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
CALLBACK_CATALOG_PREFIX = "cat:"

STUDENT_APP_PATH = "/app/"
STUDENT_HOMEWORK_PATH = "/app/homework/{assignment_id}"
STAFF_APP_PATH = "/admin/"
STAFF_ASSIGNMENT_PATH = "/admin/assignments/{assignment_id}"
BUTTON_TITLE_MAX = 48


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
        student = role == UserRole.STUDENT
        label = texts.BOT_OPEN_APP_STUDENT if student else texts.BOT_OPEN_APP_STAFF
        today = texts.BOT_BUTTON_SCHEDULE if student else texts.BOT_BUTTON_TODAY
        homework = texts.BOT_BUTTON_HOMEWORK if student else texts.BOT_BUTTON_REVIEW
        rows = [
            [KeyboardButton(text=label)],
            [KeyboardButton(text=today), KeyboardButton(text=homework)],
        ]
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


def homework_button(public_base_url: str, assignment_id: int) -> InlineKeyboardMarkup | None:
    """Инлайн-кнопка ``web_app`` «Открыть в приложении» на карточку ДЗ (docs/05 §5.3).

    ``None``, если адрес не HTTPS (Telegram не откроет Mini App).
    """
    base = public_base_url.strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    url = base + STUDENT_HOMEWORK_PATH.format(assignment_id=assignment_id)
    button = InlineKeyboardButton(text=texts.BOT_HW_OPEN, web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def staff_review_buttons(
    public_base_url: str, items: list[tuple[int, str]], role: UserRole
) -> InlineKeyboardMarkup | None:
    """Кнопки ``web_app`` «на проверку»: по одной на работу + общая «Открыть Admin App».

    Args:
        public_base_url: Адрес приложения.
        items: Пары (идентификатор выдачи, подпись кнопки).
        role: Роль сотрудника (адрес общей кнопки).

    Returns:
        ``None``, если адрес не HTTPS (Telegram не откроет Mini App).
    """
    base = public_base_url.strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    rows = [
        [
            InlineKeyboardButton(
                text=label[:BUTTON_TITLE_MAX],
                web_app=WebAppInfo(url=base + STAFF_ASSIGNMENT_PATH.format(assignment_id=item_id)),
            )
        ]
        for item_id, label in items
    ]
    general = open_app_button(role, public_base_url)
    if general is not None:
        rows += general.inline_keyboard
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def catalog_navigation(
    index: int, total: int, contact_url: str | None
) -> InlineKeyboardMarkup | None:
    """Листание каталога: «Назад» / номер / «Далее» и URL-кнопка «Связаться с преподавателем».

    ``None``, если одна карточка и контакт не настроен (кнопок нет).
    """
    nav: list[InlineKeyboardButton] = []
    if index > 0:
        nav.append(
            InlineKeyboardButton(
                text=texts.BOT_CATALOG_PREV, callback_data=f"{CALLBACK_CATALOG_PREFIX}{index - 1}"
            )
        )
    if total > 1:
        nav.append(
            InlineKeyboardButton(
                text=texts.BOT_CATALOG_POSITION.format(number=index + 1, total=total),
                callback_data=f"{CALLBACK_CATALOG_PREFIX}{index}",
            )
        )
    if index < total - 1:
        nav.append(
            InlineKeyboardButton(
                text=texts.BOT_CATALOG_NEXT, callback_data=f"{CALLBACK_CATALOG_PREFIX}{index + 1}"
            )
        )
    rows = [nav] if nav else []
    if contact_url:
        rows.append([InlineKeyboardButton(text=texts.BOT_BUTTON_CONTACT, url=contact_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def lesson_links(video_url: str | None, board_url: str | None) -> InlineKeyboardMarkup | None:
    """URL-кнопки «Телемост» и «Доска» под уроком; ``None``, если ссылок нет."""
    buttons = [
        InlineKeyboardButton(text=label, url=url)
        for label, url in (
            (texts.BOT_LINK_VIDEO, video_url),
            (texts.BOT_LINK_BOARD, board_url),
        )
        if url
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
