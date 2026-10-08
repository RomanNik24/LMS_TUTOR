"""Тесты хэндлеров бота T1.11: гость, ученик, персонал, приглашения (Telegram подменён)."""

from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as aioredis
import time_machine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.bot import keyboards
from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.models import StudentProfile, User
from src.services.auth import AuthService
from tests.integration.conftest import BOT_TOKEN, PUBLIC_BASE_URL, BotHarness

TG_STUDENT = 100_001
TG_STAFF = 100_002
TG_GUEST = 100_003
TG_OTHER = 100_004


async def _user(
    db: AsyncSession,
    role: UserRole,
    name: str,
    *,
    telegram_id: int | None = None,
    active: bool = True,
) -> User:
    user = User(role=role, display_name=name, telegram_id=telegram_id, is_active=active)
    db.add(user)
    await db.commit()
    return user


async def _invite(db: AsyncSession, redis: aioredis.Redis, owner: User, target: User) -> str:
    service = AuthService(db, SessionStore(redis), RateLimiter(redis), BOT_TOKEN)
    issued = await service.create_invite(
        CurrentUser(id=owner.id, role=owner.role, timezone=owner.timezone), target.id
    )
    return issued.token


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман", telegram_id=TG_STAFF)


def _keyboard_texts(markup: object) -> list[str]:
    rows = getattr(markup, "keyboard", None) or getattr(markup, "inline_keyboard", [])
    return [button.text for row in rows for button in row]


# ---------------------------------------------------------------- /start по состояниям


async def test_guest_start_greets_and_shows_guest_menu(harness: BotHarness) -> None:
    await harness.send_text(TG_GUEST, "/start")
    send = harness.session.of("SendMessage")[-1]
    assert send.text == texts.BOT_GUEST_GREETING
    assert _keyboard_texts(send.reply_markup) == [
        texts.BOT_BUTTON_CATALOG,
        texts.BOT_BUTTON_CONTACT,
    ]
    commands = harness.session.of("SetMyCommands")[-1]
    assert [c.command for c in commands.commands] == ["start", "help"]
    assert commands.scope.chat_id == TG_GUEST


async def test_student_start_greets_by_name_with_web_app_button(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.send_text(TG_STUDENT, "/start")
    send = harness.session.of("SendMessage")[-1]
    assert send.text == "Привет, Аня! Расписание и ДЗ — в приложении."
    button = send.reply_markup.keyboard[0][0]
    assert button.text == texts.BOT_OPEN_APP_STUDENT
    # Кнопка клавиатуры НЕ web_app: Telegram не передал бы initData (вход не сработал бы)
    assert button.web_app is None
    commands = harness.session.of("SetMyCommands")[-1]
    assert [c.command for c in commands.commands] == [
        "start",
        "app",
        "today",
        "hw",
        "web",
        "logout",
        "help",
    ]


async def test_staff_start_uses_neutral_tone_and_admin_app(
    harness: BotHarness, owner: User
) -> None:
    await harness.send_text(TG_STAFF, "/start")
    send = harness.session.of("SendMessage")[-1]
    assert send.text == texts.BOT_STAFF_GREETING.format(name="Роман")
    assert "Привет" not in send.text
    button = send.reply_markup.keyboard[0][0]
    assert button.text == texts.BOT_OPEN_APP_STAFF
    assert button.web_app is None


async def test_archived_user_is_treated_as_guest_with_closed_access(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    await _user(db_session, UserRole.STUDENT, "Архив", telegram_id=TG_STUDENT, active=False)
    await harness.send_text(TG_STUDENT, "/start")
    assert harness.session.sent_texts()[-1] == texts.BOT_ACCESS_CLOSED
    await harness.send_text(TG_STUDENT, "/web")
    assert harness.session.sent_texts()[-1] == texts.BOT_WEB_GUEST


# ---------------------------------------------------------------- приглашения


async def test_valid_invite_links_student_and_shows_student_menu(
    harness: BotHarness, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня")
    db_session.add(StudentProfile(user_id=student.id, teacher_id=owner.id))
    await db_session.commit()
    token = await _invite(db_session, redis_clean, owner, student)
    await harness.send_text(TG_GUEST, f"/start inv_{token}", username="anya")
    send = harness.session.of("SendMessage")[-1]
    assert send.text == "Привет, Аня! Расписание и ДЗ — в приложении."
    await db_session.refresh(student)
    assert student.telegram_id == TG_GUEST
    assert student.telegram_username == "anya"
    assert harness.session.of("SetMyCommands")[-1].commands[1].command == "app"


async def test_invalid_invite_token(harness: BotHarness) -> None:
    await harness.send_text(TG_GUEST, "/start inv_garbage")
    assert harness.session.sent_texts()[-1] == texts.INVITE_INVALID


async def test_used_invite_token(
    harness: BotHarness, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня")
    token = await _invite(db_session, redis_clean, owner, student)
    await harness.send_text(TG_GUEST, f"/start inv_{token}")
    await harness.send_text(TG_OTHER, f"/start inv_{token}")
    assert harness.session.sent_texts()[-1] == texts.INVITE_ALREADY_USED


async def test_expired_invite_token(
    harness: BotHarness, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня")
    token = await _invite(db_session, redis_clean, owner, student)
    with time_machine.travel(datetime.now(UTC) + timedelta(days=8), tick=False):
        await harness.send_text(TG_GUEST, f"/start inv_{token}")
    assert harness.session.sent_texts()[-1] == texts.INVITE_INVALID


async def test_invite_for_telegram_already_linked_to_other_profile(
    harness: BotHarness, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    await _user(db_session, UserRole.STUDENT, "Первый", telegram_id=TG_STUDENT)
    second = await _user(db_session, UserRole.STUDENT, "Второй")
    token = await _invite(db_session, redis_clean, owner, second)
    await harness.send_text(TG_STUDENT, f"/start inv_{token}")
    assert harness.session.sent_texts()[-1] == texts.TELEGRAM_ALREADY_LINKED


async def test_same_profile_invite_says_already_logged_in(
    harness: BotHarness, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    token = await _invite(db_session, redis_clean, owner, student)
    await harness.send_text(TG_STUDENT, f"/start inv_{token}")
    assert harness.session.sent_texts()[-1] == texts.BOT_ALREADY_LOGGED_IN


async def test_too_many_failed_invites_blocks_user(harness: BotHarness) -> None:
    for _ in range(5):
        await harness.send_text(TG_GUEST, "/start inv_bad")
    await harness.send_text(TG_GUEST, "/start inv_bad")
    assert harness.session.sent_texts()[-1] == texts.TOO_MANY_ATTEMPTS


# ---------------------------------------------------------------- перепривязка (FSM)


async def _relink_setup(db: AsyncSession, redis: aioredis.Redis, owner: User) -> tuple[User, str]:
    student = await _user(db, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    return student, await _invite(db, redis, owner, student)


async def test_relink_confirm_yes(
    harness: BotHarness, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student, token = await _relink_setup(db_session, redis_clean, owner)
    await harness.send_text(TG_OTHER, f"/start inv_{token}")
    ask = harness.session.of("SendMessage")[-1]
    assert ask.text == texts.BOT_RELINK_CONFIRM
    assert _keyboard_texts(ask.reply_markup) == [texts.BOT_RELINK_YES, texts.BOT_RELINK_CANCEL]
    await db_session.refresh(student)
    assert student.telegram_id == TG_STUDENT  # пока без изменений

    await harness.press(TG_OTHER, keyboards.CALLBACK_RELINK_YES)
    await db_session.refresh(student)
    assert student.telegram_id == TG_OTHER
    assert harness.session.of("AnswerCallbackQuery")
    assert harness.session.sent_texts()[-1] == "Привет, Аня! Расписание и ДЗ — в приложении."


async def test_relink_confirm_no_keeps_old_binding(
    harness: BotHarness, db_session: AsyncSession, owner: User, redis_clean: aioredis.Redis
) -> None:
    student, token = await _relink_setup(db_session, redis_clean, owner)
    await harness.send_text(TG_OTHER, f"/start inv_{token}")
    await harness.press(TG_OTHER, keyboards.CALLBACK_RELINK_NO)
    await db_session.refresh(student)
    assert student.telegram_id == TG_STUDENT
    assert harness.session.sent_texts()[-1] == texts.BOT_RELINK_CANCELLED
    assert harness.session.of("AnswerCallbackQuery")


async def test_relink_button_without_state_says_expired(harness: BotHarness) -> None:
    await harness.press(TG_OTHER, keyboards.CALLBACK_RELINK_YES)
    assert harness.session.sent_texts()[-1] == texts.BOT_RELINK_STATE_LOST
    assert harness.session.of("AnswerCallbackQuery")


# ---------------------------------------------------------------- /app /web /help /logout


async def test_app_command_per_role(harness: BotHarness, db_session: AsyncSession) -> None:
    await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.send_text(TG_STUDENT, "/app")
    send = harness.session.of("SendMessage")[-1]
    assert send.reply_markup.inline_keyboard[0][0].web_app.url == f"{PUBLIC_BASE_URL}/app/"
    await harness.send_text(TG_GUEST, "/app")
    assert harness.session.sent_texts()[-1] == texts.BOT_GUEST_GREETING


async def test_open_app_menu_button_sends_inline_web_app_button(
    harness: BotHarness, db_session: AsyncSession, owner: User
) -> None:
    """Текстовая кнопка меню открывает Mini App инлайн-кнопкой (она передаёт initData)."""
    await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.send_text(TG_STUDENT, texts.BOT_OPEN_APP_STUDENT)
    student_markup = harness.session.of("SendMessage")[-1].reply_markup
    assert student_markup.inline_keyboard[0][0].web_app.url == f"{PUBLIC_BASE_URL}/app/"
    await harness.send_text(TG_STAFF, texts.BOT_OPEN_APP_STAFF)
    staff_markup = harness.session.of("SendMessage")[-1].reply_markup
    assert staff_markup.inline_keyboard[0][0].web_app.url == f"{PUBLIC_BASE_URL}/admin/"


async def test_web_command_issues_one_time_link(
    harness: BotHarness, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.send_text(TG_STUDENT, "/web")
    text = harness.session.sent_texts()[-1]
    url = text.split("\n")[-1]
    assert url.startswith(f"{PUBLIC_BASE_URL}/login/")
    token = url.rsplit("/", 1)[1]
    service = AuthService(
        db_session, SessionStore(redis_clean), RateLimiter(redis_clean), BOT_TOKEN
    )
    user = await service.consume_web_login(token)
    assert user.id == student.id


async def test_web_command_for_guest(harness: BotHarness) -> None:
    await harness.send_text(TG_GUEST, "/web")
    assert harness.session.sent_texts()[-1] == texts.BOT_WEB_GUEST


async def test_help_per_state(harness: BotHarness, db_session: AsyncSession, owner: User) -> None:
    await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.send_text(TG_GUEST, "/help")
    assert harness.session.sent_texts()[-1] == texts.BOT_HELP_GUEST
    await harness.send_text(TG_STUDENT, "/help")
    assert harness.session.sent_texts()[-1] == texts.BOT_HELP_STUDENT
    await harness.send_text(TG_STAFF, "/help")
    assert harness.session.sent_texts()[-1] == texts.BOT_HELP_STAFF


async def test_logout_requires_confirmation_then_unlinks(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.send_text(TG_STUDENT, "/logout")
    assert harness.session.sent_texts()[-1] == texts.BOT_LOGOUT_CONFIRM
    await db_session.refresh(student)
    assert student.telegram_id == TG_STUDENT
    await harness.press(TG_STUDENT, keyboards.CALLBACK_LOGOUT_YES)
    await db_session.refresh(student)
    assert student.telegram_id is None
    assert harness.session.sent_texts()[-1] == texts.BOT_LOGOUT_DONE
    assert [c.command for c in harness.session.of("SetMyCommands")[-1].commands] == [
        "start",
        "help",
    ]
    assert harness.session.of("AnswerCallbackQuery")


async def test_owner_logout_is_refused(
    harness: BotHarness, db_session: AsyncSession, owner: User
) -> None:
    """Владелец не может отвязать Telegram: войти снова было бы нельзя."""
    await harness.press(TG_STAFF, keyboards.CALLBACK_LOGOUT_YES)
    assert harness.session.sent_texts()[-1] == texts.OWNER_CANNOT_UNLINK
    await db_session.refresh(owner)
    assert owner.telegram_id == TG_STAFF


async def test_logout_cancel(harness: BotHarness, db_session: AsyncSession) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.press(TG_STUDENT, keyboards.CALLBACK_LOGOUT_NO)
    await db_session.refresh(student)
    assert student.telegram_id == TG_STUDENT
    assert harness.session.sent_texts()[-1] == texts.BOT_LOGOUT_CANCELLED


# ---------------------------------------------------------------- гость и подсказки


async def test_guest_buttons_and_fallback(harness: BotHarness) -> None:
    await harness.send_text(TG_GUEST, texts.BOT_BUTTON_CATALOG)
    assert harness.session.sent_texts()[-1] == texts.BOT_CATALOG_EMPTY
    await harness.send_text(TG_GUEST, texts.BOT_BUTTON_CONTACT)
    contact = harness.session.of("SendMessage")[-1]
    assert contact.reply_markup.inline_keyboard[0][0].url == "https://t.me/teacher"
    await harness.send_text(TG_GUEST, "что-то непонятное")
    assert harness.session.sent_texts()[-1] == texts.BOT_FALLBACK_HINT


# ---------------------------------------------------------------- блокировка бота, ошибки


async def test_my_chat_member_sets_and_clears_bot_blocked(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    student = await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)
    await harness.chat_member(TG_STUDENT, "kicked")
    await db_session.refresh(student)
    assert student.bot_blocked is True
    await harness.chat_member(TG_STUDENT, "member")
    await db_session.refresh(student)
    assert student.bot_blocked is False
    unknown = (await db_session.execute(select(User).where(User.telegram_id == 999))).first()
    assert unknown is None
    await harness.chat_member(999, "kicked")  # неизвестный пользователь — без ошибок


async def test_unexpected_error_gets_neutral_reply(
    harness: BotHarness,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _user(db_session, UserRole.STUDENT, "Аня", telegram_id=TG_STUDENT)

    async def boom(self: AuthService, actor: CurrentUser) -> None:
        raise RuntimeError("секретная внутренняя причина")

    monkeypatch.setattr(AuthService, "create_web_login_link", boom)
    await harness.send_text(TG_STUDENT, "/web")
    assert harness.session.sent_texts()[-1] == texts.BOT_ERROR_GENERIC
    assert "секретная" not in harness.session.sent_texts()[-1]
    assert any(record.levelname == "ERROR" for record in caplog.records)
