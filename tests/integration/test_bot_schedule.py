"""Бот: /today и кнопки «Расписание» / «Сегодня» (T3.08)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from sqlalchemy.ext.asyncio import AsyncSession
from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.db.models import StudentProfile, Subject, User
from src.schemas.schedule import LessonCancel, LessonCreate
from src.services.schedule import ScheduleService
from tests.integration.conftest import BotHarness

pytestmark = pytest.mark.security

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)  # 15:00 в Москве
TG_STUDENT = 100_001
TG_STAFF = 100_002
TG_GUEST = 100_003


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


async def _user(
    db: AsyncSession, role: UserRole, name: str, telegram_id: int | None = None
) -> User:
    user = User(role=role, display_name=name, telegram_id=telegram_id)
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман", TG_STAFF)


@pytest.fixture
async def anya(db_session: AsyncSession, owner: User) -> User:
    user = await _user(db_session, UserRole.STUDENT, "Аня", TG_STUDENT)
    db_session.add(
        StudentProfile(
            user_id=user.id,
            teacher_id=owner.id,
            video_url="https://telemost.yandex.ru/profile",
            board_url="https://miro.com/profile",
        )
    )
    await db_session.commit()
    return user


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add(Subject(code="informatics", name="Информатика"))
    await db_session.commit()


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


async def _lesson(
    db: AsyncSession, owner: User, student: User, hours: float, **extra: object
) -> int:
    start = NOW + timedelta(hours=hours)
    item = await ScheduleService(db).create_lesson(
        _actor(owner),
        LessonCreate.model_validate(
            {
                "subject_code": "informatics",
                "student_ids": [student.id],
                "start_at": start,
                "end_at": start + timedelta(hours=1),
                **extra,
            }
        ),
    )
    return item.id


def _buttons(markup: object) -> list[tuple[str, str | None]]:
    rows = getattr(markup, "inline_keyboard", [])
    return [(b.text, b.url) for row in rows for b in row]


# ---------------------------------------------------------------- ученик


async def test_student_gets_lessons_for_next_24_hours_with_links(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    await _lesson(db_session, owner, anya, 2, topic="Графы")  # 17:00 по Москве
    await _lesson(db_session, owner, anya, 5, board_url_override="https://miro.com/lesson")
    await _lesson(db_session, owner, anya, 30)  # дальше суток
    await harness.send_text(TG_STUDENT, "/today")
    sent = harness.session.of("SendMessage")
    assert len(sent) == 2
    assert sent[0].text == "вт, 6 окт, 17:00–18:00\nИнформатика\nГрафы"
    assert _buttons(sent[0].reply_markup) == [
        (texts.BOT_LINK_VIDEO, "https://telemost.yandex.ru/profile"),
        (texts.BOT_LINK_BOARD, "https://miro.com/profile"),
    ]
    # ссылка урока важнее профиля
    assert _buttons(sent[1].reply_markup)[-1] == (texts.BOT_LINK_BOARD, "https://miro.com/lesson")


async def test_student_schedule_button_works_like_command(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    await _lesson(db_session, owner, anya, 1)
    await harness.send_text(TG_STUDENT, texts.BOT_BUTTON_SCHEDULE)
    assert len(harness.session.of("SendMessage")) == 1


async def test_student_without_lessons_and_cancelled_lessons_are_hidden(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    await harness.send_text(TG_STUDENT, "/today")
    assert harness.session.sent_texts()[-1] == texts.BOT_STUDENT_NO_LESSONS
    lesson_id = await _lesson(db_session, owner, anya, 2)
    await ScheduleService(db_session).cancel_lesson(_actor(owner), lesson_id, LessonCancel())
    await harness.send_text(TG_STUDENT, "/today")
    assert harness.session.sent_texts()[-1] == texts.BOT_STUDENT_NO_LESSONS


async def test_student_sees_time_in_own_timezone(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    anya.timezone = "Asia/Yekaterinburg"  # UTC+5: 14:00 UTC = 19:00
    await db_session.commit()
    await _lesson(db_session, owner, anya, 2)
    await harness.send_text(TG_STUDENT, "/today")
    assert harness.session.sent_texts()[-1].startswith("вт, 6 окт, 19:00–20:00")


async def test_student_message_has_no_private_data(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    await _lesson(db_session, owner, anya, 2)
    await harness.send_text(TG_STUDENT, "/today")
    text = harness.session.sent_texts()[-1]
    assert "Роман" not in text
    assert "₽" not in text


# ---------------------------------------------------------------- персонал и гость


async def test_staff_gets_compact_day_summary(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    first = await _lesson(db_session, owner, anya, 2)  # 17:00
    await _lesson(db_session, owner, anya, 4)  # 19:00
    await _lesson(db_session, owner, anya, 20)  # завтра
    await ScheduleService(db_session).cancel_lesson(_actor(owner), first, LessonCancel())
    await harness.send_text(TG_STAFF, texts.BOT_BUTTON_TODAY)
    text = harness.session.sent_texts()[-1]
    assert text == (
        "Сегодня, вт, 6 окт:\n"
        f"17:00 Информатика: Аня ({texts.BOT_LESSON_CANCELLED_MARK})\n"
        "19:00 Информатика: Аня"
    )


async def test_staff_without_lessons(harness: BotHarness, owner: User) -> None:
    await harness.send_text(TG_STAFF, "/today")
    assert harness.session.sent_texts()[-1] == texts.BOT_STAFF_NO_LESSONS


async def test_guest_gets_greeting(harness: BotHarness) -> None:
    await harness.send_text(TG_GUEST, "/today")
    assert harness.session.sent_texts()[-1] == texts.BOT_GUEST_GREETING


async def test_menu_has_schedule_buttons(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    await harness.send_text(TG_STUDENT, "/start")
    student_menu = harness.session.of("SendMessage")[-1].reply_markup.keyboard
    assert [b.text for row in student_menu for b in row] == [
        texts.BOT_OPEN_APP_STUDENT,
        texts.BOT_BUTTON_SCHEDULE,
    ]
    await harness.send_text(TG_STAFF, "/start")
    staff_menu = harness.session.of("SendMessage")[-1].reply_markup.keyboard
    assert [b.text for row in staff_menu for b in row] == [
        texts.BOT_OPEN_APP_STAFF,
        texts.BOT_BUTTON_TODAY,
    ]
