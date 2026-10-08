"""Кнопка «Каталог услуг» с листанием карточек (docs/05 §3.4, T8.02).

Карточки читает ``CatalogService.list_published`` (доступно и гостю). Листание — по номеру
карточки в ``callback_data`` (``cat:<номер>``); сообщение обновляется через ``edit_text``, а список
перечитывается при каждом нажатии: если каталог изменился, номер приводится к допустимому.
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from src.bot import keyboards
from src.core import texts
from src.core.config import Settings
from src.schemas.catalog import CatalogItemPublic
from src.services.catalog import CatalogService


def render_card(item: CatalogItemPublic) -> str:
    """Текст карточки: название, описание, стоимость текстом (если есть)."""
    parts = [item.title, item.description]
    if item.price_text:
        parts.append(item.price_text)
    return "\n\n".join(parts)


def _clamp(index: int, total: int) -> int:
    return max(0, min(index, total - 1))


def _markup(index: int, total: int, contact_url: str) -> InlineKeyboardMarkup | None:
    return keyboards.catalog_navigation(index, total, contact_url.strip() or None)


async def open_catalog(message: Message, session: AsyncSession, settings: Settings) -> None:
    """Первая карточка каталога либо сообщение «скоро появится»."""
    items = await CatalogService(session).list_published()
    if not items:
        await message.answer(texts.BOT_CATALOG_EMPTY)
        return
    await message.answer(
        render_card(items[0]), reply_markup=_markup(0, len(items), settings.teacher_contact_url)
    )


async def turn_page(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    """Перелистывание: карточка с номером из ``callback_data``."""
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message) or callback.data is None:
        return
    items = await CatalogService(session).list_published()
    if not items:
        await message.edit_text(texts.BOT_CATALOG_EMPTY)
        return
    try:
        requested = int(callback.data.removeprefix(keyboards.CALLBACK_CATALOG_PREFIX))
    except ValueError:
        requested = 0
    index = _clamp(requested, len(items))
    await message.edit_text(
        render_card(items[index]),
        reply_markup=_markup(index, len(items), settings.teacher_contact_url),
    )


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``)."""
    router = Router(name="catalog")
    router.message.register(open_catalog, F.text == texts.BOT_BUTTON_CATALOG)
    router.callback_query.register(turn_page, F.data.startswith(keyboards.CALLBACK_CATALOG_PREFIX))
    return router
