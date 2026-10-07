"""``my_chat_member``: пользователь заблокировал или разблокировал бота (docs/05 §7)."""

from aiogram import Router
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.profile import ProfileService

_KICKED = "kicked"
_MEMBER = "member"


async def my_chat_member(event: ChatMemberUpdated, session: AsyncSession) -> None:
    """``kicked`` → ``bot_blocked = true``; ``member`` → ``false``."""
    status = event.new_chat_member.status
    if status not in (_KICKED, _MEMBER):
        return
    await ProfileService(session).set_bot_blocked(event.from_user.id, status == _KICKED)


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``: роутер нельзя подключить дважды)."""
    router = Router(name="membership")
    router.my_chat_member.register(my_chat_member)
    return router
