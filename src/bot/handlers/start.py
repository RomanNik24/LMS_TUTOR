"""``/start`` и принятие приглашения ``/start inv_<token>`` (docs/05 §3.1)."""

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from src.bot import keyboards
from src.bot.commands import set_commands
from src.bot.handlers.common import greeting_for
from src.bot.states import ConfirmRelinkState
from src.core import texts
from src.core.config import Settings
from src.core.constants import BOT_INVITE_PAYLOAD_PREFIX
from src.core.current_user import CurrentUser
from src.core.exceptions import AppError
from src.core.security import hash_token
from src.services.auth import AuthService, InviteAcceptResult, InviteAcceptStatus

_FSM_TOKEN_HASH = "invite_token_hash"  # noqa: S105 - ключ данных FSM, не секрет
_FSM_USERNAME = "telegram_username"


async def _show_linked(
    message: Message,
    bot: Bot,
    result: InviteAcceptResult,
    current_user: CurrentUser | None,
    settings: Settings,
) -> None:
    """Приветствие после успешной привязки (или «ты уже в системе»)."""
    chat_id = message.chat.id
    if current_user is not None and current_user.id == result.user_id:
        text = texts.BOT_ALREADY_LOGGED_IN
    else:
        text = greeting_for(result.role, result.display_name)
    await set_commands(bot, chat_id, result.role)
    await message.answer(
        text, reply_markup=keyboards.main_menu(result.role, settings.public_base_url)
    )


async def start(
    message: Message,
    command: CommandObject,
    bot: Bot,
    state: FSMContext,
    auth: AuthService,
    settings: Settings,
    current_user: CurrentUser | None,
    display_name: str | None,
    access_closed: bool,
) -> None:
    """Приветствие по состоянию либо принятие приглашения."""
    payload = (command.args or "").strip()
    if payload.startswith(BOT_INVITE_PAYLOAD_PREFIX):
        await _accept_invite(
            message, bot, state, auth, settings, current_user,
            payload[len(BOT_INVITE_PAYLOAD_PREFIX):],
        )  # fmt: skip
        return
    role = current_user.role if current_user else None
    await set_commands(bot, message.chat.id, role)
    if access_closed:
        text = texts.BOT_ACCESS_CLOSED
    elif current_user is not None and display_name is not None:
        text = greeting_for(current_user.role, display_name)
    else:
        text = texts.BOT_GUEST_GREETING
    await message.answer(text, reply_markup=keyboards.main_menu(role, settings.public_base_url))


async def _accept_invite(
    message: Message,
    bot: Bot,
    state: FSMContext,
    auth: AuthService,
    settings: Settings,
    current_user: CurrentUser | None,
    token: str,
) -> None:
    """Принять приглашение; при другом привязанном Telegram — запросить подтверждение."""
    if message.from_user is None:
        return
    username = message.from_user.username
    try:
        result = await auth.accept_invite(token, message.from_user.id, username)
    except AppError as error:
        await message.answer(error.message)
        return
    if result.status == InviteAcceptStatus.RELINK_REQUIRED:
        await state.set_state(ConfirmRelinkState.waiting_confirm)
        await state.update_data({_FSM_TOKEN_HASH: hash_token(token), _FSM_USERNAME: username})
        await message.answer(texts.BOT_RELINK_CONFIRM, reply_markup=keyboards.relink_confirm())
        return
    await state.clear()
    await _show_linked(message, bot, result, current_user, settings)


async def relink_yes(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    auth: AuthService,
    settings: Settings,
    current_user: CurrentUser | None,
) -> None:
    """Подтверждение перепривязки: старая привязка снимается."""
    await callback.answer()
    data = await state.get_data()
    token_hash = data.get(_FSM_TOKEN_HASH)
    message = callback.message
    if not isinstance(token_hash, str) or not isinstance(message, Message):
        await state.clear()
        return
    await state.clear()
    try:
        result = await auth.confirm_relink_by_hash(
            token_hash, callback.from_user.id, data.get(_FSM_USERNAME)
        )
    except AppError as error:
        await message.answer(error.message)
        return
    await _show_linked(message, bot, result, current_user, settings)


async def relink_no(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена перепривязки."""
    await callback.answer()
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.answer(texts.BOT_RELINK_CANCELLED)


async def relink_state_lost(callback: CallbackQuery) -> None:
    """Нажатие кнопки после истечения состояния FSM (TTL 1 час)."""
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(texts.BOT_RELINK_STATE_LOST)


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``: роутер нельзя подключить дважды)."""
    router = Router(name="start")
    router.message.register(start, CommandStart())
    router.callback_query.register(
        relink_yes, ConfirmRelinkState.waiting_confirm, F.data == keyboards.CALLBACK_RELINK_YES
    )
    router.callback_query.register(
        relink_no, ConfirmRelinkState.waiting_confirm, F.data == keyboards.CALLBACK_RELINK_NO
    )
    router.callback_query.register(
        relink_state_lost, F.data.in_({keyboards.CALLBACK_RELINK_YES, keyboards.CALLBACK_RELINK_NO})
    )
    return router
