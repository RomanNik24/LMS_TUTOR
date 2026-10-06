"""Состояния FSM бота (docs/05 §4). Хранятся в Redis с TTL 1 час."""

from aiogram.fsm.state import State, StatesGroup


class ConfirmRelinkState(StatesGroup):
    """Подтверждение перепривязки Telegram по приглашению."""

    waiting_confirm = State()
