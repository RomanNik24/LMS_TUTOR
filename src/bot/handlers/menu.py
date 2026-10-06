"""Команды ``/app``, ``/web``, ``/logout``, ``/help``, кнопки гостя и подсказка (docs/05 §2–§3)."""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from src.bot import keyboards
from src.bot.commands import set_commands
from src.core import texts
from src.core.config import Settings
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import AppError
from src.services.auth import AuthService


async def open_app(message: Message, settings: Settings, current_user: CurrentUser | None) -> None:
    """Кнопка открытия Student App / Admin App."""
    if current_user is None:
        await message.answer(texts.BOT_GUEST_GREETING)
        return
    markup = keyboards.open_app_button(current_user.role, settings.public_base_url)
    if markup is None:
        await message.answer(texts.BOT_APP_UNAVAILABLE)
        return
    label = (
        texts.BOT_OPEN_APP_STUDENT
        if current_user.role == UserRole.STUDENT
        else texts.BOT_OPEN_APP_STAFF
    )
    await message.answer(label, reply_markup=markup)


async def web_login(
    message: Message, auth: AuthService, settings: Settings, current_user: CurrentUser | None
) -> None:
    """Одноразовая ссылка входа в браузере (10 минут)."""
    if current_user is None:
        await message.answer(texts.BOT_WEB_GUEST)
        return
    issued = await auth.create_web_login_link(current_user)
    url = f"{settings.public_base_url.rstrip('/')}/login/{issued.token}"
    await message.answer(texts.BOT_WEB_LINK.format(url=url))


async def help_command(message: Message, current_user: CurrentUser | None) -> None:
    """Справка по состоянию пользователя."""
    if current_user is None:
        text = texts.BOT_HELP_GUEST
    elif current_user.role == UserRole.STUDENT:
        text = texts.BOT_HELP_STUDENT
    else:
        text = texts.BOT_HELP_STAFF
    await message.answer(text)


async def logout(message: Message, current_user: CurrentUser | None) -> None:
    """Запрос подтверждения выхода (отвязки аккаунта)."""
    if current_user is None:
        await message.answer(texts.BOT_GUEST_GREETING)
        return
    await message.answer(texts.BOT_LOGOUT_CONFIRM, reply_markup=keyboards.logout_confirm())


async def logout_yes(
    callback: CallbackQuery,
    bot: Bot,
    auth: AuthService,
    settings: Settings,
    state: FSMContext,
    current_user: CurrentUser | None,
) -> None:
    """Подтверждённый выход: ``telegram_id = NULL``, переход в состояние гостя."""
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return
    if current_user is None:
        await message.answer(texts.BOT_LOGOUT_DONE)
        return
    try:
        await auth.unlink_telegram(current_user, current_user.id)
    except AppError as error:
        await message.answer(error.message)
        return
    await state.clear()
    await set_commands(bot, message.chat.id, None)
    await message.answer(
        texts.BOT_LOGOUT_DONE, reply_markup=keyboards.main_menu(None, settings.public_base_url)
    )


async def logout_no(callback: CallbackQuery) -> None:
    """Отмена выхода."""
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(texts.BOT_LOGOUT_CANCELLED)


async def catalog(message: Message) -> None:
    """Каталог услуг: пока пуст (карточки появятся позже, docs/05 §3.4)."""
    await message.answer(texts.BOT_CATALOG_EMPTY)


async def contact(message: Message, settings: Settings) -> None:
    """Ссылка на личный Telegram преподавателя (``TEACHER_CONTACT_URL``)."""
    url = settings.teacher_contact_url.strip()
    if not url:
        await message.answer(texts.BOT_CONTACT_UNAVAILABLE)
        return
    await message.answer(texts.BOT_CONTACT, reply_markup=keyboards.contact_button(url))


async def fallback(message: Message) -> None:
    """Любое сообщение вне сценария получает подсказку."""
    await message.answer(texts.BOT_FALLBACK_HINT)


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``: роутер нельзя подключить дважды)."""
    router = Router(name="menu")
    router.message.register(open_app, Command("app"))
    router.message.register(
        open_app, F.text.in_({texts.BOT_OPEN_APP_STUDENT, texts.BOT_OPEN_APP_STAFF})
    )
    router.message.register(web_login, Command("web"))
    router.message.register(help_command, Command("help"))
    router.message.register(logout, Command("logout"))
    router.callback_query.register(logout_yes, F.data == keyboards.CALLBACK_LOGOUT_YES)
    router.callback_query.register(logout_no, F.data == keyboards.CALLBACK_LOGOUT_NO)
    router.message.register(catalog, F.text == texts.BOT_BUTTON_CATALOG)
    router.message.register(contact, F.text == texts.BOT_BUTTON_CONTACT)
    router.message.register(fallback)
    return router
