"""Тесты запуска бота (polling/webhook), webhook-эндпоинта и клиента Telegram (T1.11)."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
import pytest
import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.bot import runtime as runtime_module
from src.bot.client import build_bot
from src.bot.dispatcher import create_dispatcher
from src.bot.runtime import BotRuntime, start_bot, webhook_path_secret, webhook_target_url
from src.core import config as config_module
from src.core import texts
from src.main import create_app
from tests.integration.conftest import (
    BOT_TOKEN,
    PUBLIC_BASE_URL,
    BotHarness,
    FakeTelegramSession,
    make_settings,
)

SECRET = "w" * 40  # noqa: S105 - тестовый секрет
WEBHOOK_BASE = "https://lms.example.com/telegram/webhook"


def _scope_for(db: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Контекст сессии, отдающий тестовую сессию БД."""

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        yield db

    return scope


def _unused_scope() -> AbstractAsyncContextManager[AsyncSession]:
    """Контекст сессии, который в тесте не должен вызываться."""
    raise AssertionError("сессия БД не должна открываться")


# ---------------------------------------------------------------- клиент Telegram


def test_no_token_means_no_bot() -> None:
    assert build_bot(make_settings(BOT_TOKEN=SecretStr(""))) is None


def test_client_uses_api_base_and_proxy() -> None:
    settings = make_settings(
        TELEGRAM_API_BASE="https://tg.example.net",
        TELEGRAM_PROXY_URL=SecretStr("http://proxy.example.net:3128"),
    )
    bot = build_bot(settings)
    assert bot is not None
    assert bot.session.api.base.startswith("https://tg.example.net/")
    assert bot.session.proxy == "http://proxy.example.net:3128"


def test_default_client_uses_official_api() -> None:
    bot = build_bot(make_settings())
    assert bot is not None
    assert bot.session.api.base.startswith("https://api.telegram.org/")
    assert bot.session.proxy is None


# ---------------------------------------------------------------- настройки webhook-режима


def test_webhook_mode_requires_url_and_secret() -> None:
    with pytest.raises(ValueError, match="WEBHOOK_URL"):
        make_settings(BOT_MODE="webhook")
    with pytest.raises(ValueError, match="WEBHOOK_URL"):
        make_settings(
            BOT_MODE="webhook", WEBHOOK_URL="http://insecure", WEBHOOK_SECRET=SecretStr(SECRET)
        )
    ok = make_settings(
        BOT_MODE="webhook", WEBHOOK_URL=WEBHOOK_BASE, WEBHOOK_SECRET=SecretStr(SECRET)
    )
    assert ok.bot_mode == "webhook"


def test_webhook_mode_without_token_is_allowed() -> None:
    settings = make_settings(BOT_MODE="webhook", BOT_TOKEN=SecretStr(""))
    assert settings.bot_mode == "webhook"


def test_webhook_path_secret_is_derived_and_stable() -> None:
    first = webhook_path_secret(SECRET)
    assert first == webhook_path_secret(SECRET)
    assert first != webhook_path_secret(SECRET + "x")
    assert SECRET not in first
    assert len(first) == 32


# ---------------------------------------------------------------- start_bot


async def test_start_bot_without_token_returns_none(redis_clean: aioredis.Redis) -> None:
    settings = make_settings(BOT_TOKEN=SecretStr(""))
    assert await start_bot(settings, redis_clean, _unused_scope) is None


async def test_start_bot_webhook_registers_webhook(
    monkeypatch: pytest.MonkeyPatch, redis_clean: aioredis.Redis, db_session: AsyncSession
) -> None:
    session = FakeTelegramSession()
    monkeypatch.setattr(
        runtime_module, "build_bot", lambda settings: Bot(BOT_TOKEN, session=session)
    )
    settings = make_settings(
        BOT_MODE="webhook", WEBHOOK_URL=WEBHOOK_BASE, WEBHOOK_SECRET=SecretStr(SECRET)
    )
    runtime = await start_bot(settings, redis_clean, _scope_for(db_session))
    assert runtime is not None
    assert runtime.polling_task is None
    call = session.of("SetWebhook")[0]
    assert call.url == webhook_target_url(settings)
    assert call.url.startswith(WEBHOOK_BASE + "/")
    assert call.secret_token == SECRET
    assert set(call.allowed_updates) == {"message", "callback_query", "my_chat_member"}
    await runtime.stop()


async def test_start_bot_polling_starts_and_stops_task(
    monkeypatch: pytest.MonkeyPatch, redis_clean: aioredis.Redis, db_session: AsyncSession
) -> None:
    session = FakeTelegramSession()
    monkeypatch.setattr(
        runtime_module, "build_bot", lambda settings: Bot(BOT_TOKEN, session=session)
    )
    started = asyncio.Event()

    async def fake_polling(self: Dispatcher, bot: Bot, **kwargs: object) -> None:
        assert kwargs["handle_signals"] is False
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(Dispatcher, "start_polling", fake_polling)
    runtime = await start_bot(make_settings(), redis_clean, _scope_for(db_session))
    assert runtime is not None
    assert runtime.polling_task is not None
    await asyncio.wait_for(started.wait(), timeout=2)
    assert session.of("DeleteWebhook")
    await runtime.stop()
    assert runtime.polling_task.cancelled() or runtime.polling_task.done()


def test_dispatcher_uses_redis_fsm_with_one_hour_ttl(redis_clean: aioredis.Redis) -> None:
    dispatcher = create_dispatcher(make_settings(), redis_clean, _unused_scope)
    storage = dispatcher.fsm.storage
    assert isinstance(storage, RedisStorage)
    assert storage.state_ttl == 3600
    assert storage.data_ttl == 3600


# ---------------------------------------------------------------- webhook-эндпоинт


@pytest.fixture
def webhook_app(
    harness: BotHarness,
    db_session: AsyncSession,
    redis_clean: aioredis.Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("PUBLIC_BASE_URL", PUBLIC_BASE_URL)
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("WEBHOOK_URL", WEBHOOK_BASE)
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("SENTRY_DSN", "")
    config_module.get_settings.cache_clear()
    app = create_app("local")
    app.state.bot_runtime = BotRuntime(bot=harness.bot, dispatcher=harness.dispatcher)
    app.dependency_overrides[deps.get_redis] = lambda: redis_clean
    yield app
    config_module.get_settings.cache_clear()


def _update_json(telegram_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1_790_000_000,
            "chat": {"id": telegram_id, "type": "private"},
            "from": {"id": telegram_id, "is_bot": False, "first_name": "Т"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(text)}],
        },
    }


async def _post(
    app: FastAPI, path_secret: str, header: str | None, body: dict[str, object]
) -> httpx.Response:
    headers = {} if header is None else {"X-Telegram-Bot-Api-Secret-Token": header}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(f"/telegram/webhook/{path_secret}", json=body, headers=headers)


async def test_webhook_accepts_valid_update(webhook_app: FastAPI, harness: BotHarness) -> None:
    response = await _post(
        webhook_app, webhook_path_secret(SECRET), SECRET, _update_json(555_001, "/start")
    )
    assert response.status_code == 200
    assert harness.session.sent_texts()[-1] == texts.BOT_GUEST_GREETING


async def test_webhook_rejects_wrong_header_403(webhook_app: FastAPI, harness: BotHarness) -> None:
    path = webhook_path_secret(SECRET)
    missing = await _post(webhook_app, path, None, _update_json(555_002, "/start"))
    wrong = await _post(webhook_app, path, "nope", _update_json(555_002, "/start"))
    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert harness.session.sent_texts() == []


async def test_webhook_rejects_wrong_path_404(webhook_app: FastAPI, harness: BotHarness) -> None:
    response = await _post(webhook_app, "wrong-secret", SECRET, _update_json(555_003, "/start"))
    assert response.status_code == 404
    assert harness.session.sent_texts() == []


async def test_webhook_without_bot_is_404(webhook_app: FastAPI) -> None:
    webhook_app.state.bot_runtime = None
    response = await _post(
        webhook_app, webhook_path_secret(SECRET), SECRET, _update_json(555_004, "/start")
    )
    assert response.status_code == 404


async def test_webhook_is_not_in_openapi(webhook_app: FastAPI) -> None:
    assert not any(path.startswith("/telegram") for path in webhook_app.openapi()["paths"])


async def test_app_starts_without_bot_token(
    monkeypatch: pytest.MonkeyPatch, redis_url: str
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("SENTRY_DSN", "")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("OWNER_TELEGRAM_ID", raising=False)
    config_module.get_settings.cache_clear()
    app = create_app("local")
    try:
        async with app.router.lifespan_context(app):
            assert app.state.bot_runtime is None
    finally:
        config_module.get_settings.cache_clear()
