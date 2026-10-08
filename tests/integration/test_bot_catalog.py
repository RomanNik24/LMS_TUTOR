"""Бот: «Каталог услуг» с листанием (T8.02, docs/05 §3.4)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from src.bot import keyboards
from src.core import texts
from src.db.models import CatalogItem
from tests.integration.conftest import TEACHER_URL, BotHarness

TG_GUEST = 100_201


async def add_cards(db: AsyncSession) -> None:
    db.add_all(
        [
            CatalogItem(
                title="ЕГЭ по информатике",
                description="Подготовка с нуля",
                price_text="от 1500 ₽",
                sort_order=1,
                is_published=True,
            ),
            CatalogItem(title="Скрытая", description="Черновик", sort_order=0),
            CatalogItem(
                title="ОГЭ по математике",
                description="Разбор вариантов",
                sort_order=2,
                is_published=True,
            ),
            CatalogItem(title="Олимпиады", description="Задачи", sort_order=3, is_published=True),
        ]
    )
    await db.commit()


def buttons(markup: Any) -> list[tuple[str, str | None]]:
    return [(b.text, b.callback_data or b.url) for row in markup.inline_keyboard for b in row]


async def test_empty_catalog_says_coming_soon(harness: BotHarness) -> None:
    await harness.send_text(TG_GUEST, texts.BOT_BUTTON_CATALOG)

    assert harness.session.sent_texts()[-1] == texts.BOT_CATALOG_EMPTY


async def test_guest_sees_first_published_card_without_hidden(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    await add_cards(db_session)

    await harness.send_text(TG_GUEST, texts.BOT_BUTTON_CATALOG)

    sent = harness.session.of("SendMessage")[-1]
    assert sent.text == "ЕГЭ по информатике\n\nПодготовка с нуля\n\nот 1500 ₽"
    assert "Скрытая" not in sent.text
    assert buttons(sent.reply_markup) == [
        ("1 / 3", "cat:0"),
        (texts.BOT_CATALOG_NEXT, "cat:1"),
        (texts.BOT_BUTTON_CONTACT, TEACHER_URL),
    ]


async def test_paging_edits_message_in_place(harness: BotHarness, db_session: AsyncSession) -> None:
    await add_cards(db_session)

    await harness.press(TG_GUEST, "cat:1")
    middle = harness.session.of("EditMessageText")[-1]
    await harness.press(TG_GUEST, "cat:2")
    last = harness.session.of("EditMessageText")[-1]

    assert middle.text == "ОГЭ по математике\n\nРазбор вариантов"
    assert [text for text, _ in buttons(middle.reply_markup)[:3]] == [
        texts.BOT_CATALOG_PREV,
        "2 / 3",
        texts.BOT_CATALOG_NEXT,
    ]
    assert last.text.startswith("Олимпиады")
    assert texts.BOT_CATALOG_NEXT not in [text for text, _ in buttons(last.reply_markup)]
    assert harness.session.of("SendMessage") == []  # листание не плодит сообщения


async def test_out_of_range_and_garbage_page_are_clamped(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    await add_cards(db_session)

    await harness.press(TG_GUEST, "cat:99")
    assert harness.session.of("EditMessageText")[-1].text.startswith("Олимпиады")
    await harness.press(TG_GUEST, "cat:abc")
    assert harness.session.of("EditMessageText")[-1].text.startswith("ЕГЭ по информатике")
    await harness.press(TG_GUEST, "cat:-5")
    assert harness.session.of("EditMessageText")[-1].text.startswith("ЕГЭ по информатике")


async def test_catalog_emptied_while_open(harness: BotHarness) -> None:
    await harness.press(TG_GUEST, "cat:0")

    assert harness.session.of("EditMessageText")[-1].text == texts.BOT_CATALOG_EMPTY


async def test_single_card_has_only_contact_button(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    db_session.add(CatalogItem(title="Одна", description="Карточка", is_published=True))
    await db_session.commit()

    await harness.send_text(TG_GUEST, texts.BOT_BUTTON_CATALOG)

    markup = harness.session.of("SendMessage")[-1].reply_markup
    assert buttons(markup) == [(texts.BOT_BUTTON_CONTACT, TEACHER_URL)]
    assert keyboards.catalog_navigation(0, 1, None) is None
