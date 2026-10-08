"""Команда ``/hw`` и кнопки «Мои ДЗ» / «На проверку» (docs/05 §2, §3.6, §5.1).

Аудит 2026-10-08, п. 5: по docs/05 команда и кнопки должны были появиться вместе с ДЗ (этап 4).
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from sqlalchemy.ext.asyncio import AsyncSession
from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import DueMode, HomeworkKind, UserRole
from src.db.models import StudentProfile, Subject, User
from src.schemas.homework import HomeworkCreate, SubmitRequest
from src.services.homework import HomeworkService
from src.services.submissions import SubmissionService
from tests.integration.conftest import PUBLIC_BASE_URL, BotHarness

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)  # 15:00 в Москве
TG_STUDENT = 100_011
TG_STAFF = 100_012


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


async def _user(db: AsyncSession, role: UserRole, name: str, telegram_id: int) -> User:
    user = User(role=role, display_name=name, telegram_id=telegram_id)
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    db_session.add(Subject(code="informatics", name="Информатика"))
    await db_session.commit()
    return await _user(db_session, UserRole.OWNER, "Роман", TG_STAFF)


@pytest.fixture
async def anya(db_session: AsyncSession, owner: User) -> User:
    user = await _user(db_session, UserRole.STUDENT, "Аня", TG_STUDENT)
    db_session.add(StudentProfile(user_id=user.id, teacher_id=owner.id))
    await db_session.commit()
    return user


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


async def _assign(db: AsyncSession, owner: User, student: User, title: str) -> int:
    item = await HomeworkService(db).create_homework(
        _actor(owner),
        HomeworkCreate(
            kind=HomeworkKind.REGULAR,
            title=title,
            subject_code="informatics",
            max_score=5,
            due_mode=DueMode.FIXED,
            due_at=NOW + timedelta(days=2),
            student_ids=[student.id],
        ),
    )
    return item.assignments[0].id


async def test_student_hw_lists_active_homework_with_deep_link(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    assignment_id = await _assign(db_session, owner, anya, "Задачи 1-5")
    await harness.send_text(TG_STUDENT, "/hw")
    send = harness.session.of("SendMessage")[-1]
    # срок 8 окт 12:00 UTC = 15:00 по Москве (пояс ученика по умолчанию)
    assert send.text == "«Задачи 1-5»\nСдать до чт, 8 окт, 15:00"
    button = send.reply_markup.inline_keyboard[0][0]
    assert button.text == texts.BOT_HW_OPEN
    assert button.web_app.url == f"{PUBLIC_BASE_URL}/app/homework/{assignment_id}"


async def test_student_homework_button_without_homework(
    harness: BotHarness, owner: User, anya: User
) -> None:
    await harness.send_text(TG_STUDENT, texts.BOT_BUTTON_HOMEWORK)
    assert harness.session.sent_texts()[-1] == texts.BOT_HW_STUDENT_EMPTY


async def test_staff_hw_shows_review_queue(
    harness: BotHarness, db_session: AsyncSession, owner: User, anya: User
) -> None:
    await harness.send_text(TG_STAFF, texts.BOT_BUTTON_REVIEW)
    assert harness.session.sent_texts()[-1] == texts.BOT_HW_QUEUE_EMPTY

    assignment_id = await _assign(db_session, owner, anya, "Задачи 1-5")
    await SubmissionService(db_session).submit_self_reported(
        _actor(anya), assignment_id, SubmitRequest()
    )
    await harness.send_text(TG_STAFF, "/hw")
    send = harness.session.of("SendMessage")[-1]
    assert send.text == "На проверку: 1\n«Задачи 1-5» — Аня, вт, 6 окт, 15:00"
    assert send.reply_markup.inline_keyboard[0][0].web_app.url == f"{PUBLIC_BASE_URL}/admin/"


async def test_guest_hw_gets_guest_greeting(harness: BotHarness) -> None:
    await harness.send_text(100_099, "/hw")
    assert harness.session.sent_texts()[-1] == texts.BOT_GUEST_GREETING
