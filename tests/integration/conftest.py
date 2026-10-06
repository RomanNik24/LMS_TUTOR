"""Фикстуры тестов бота (T1.11): Telegram подменён, исходящие вызовы записываются."""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest
import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import Update
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from src.bot.dispatcher import create_dispatcher
from src.core.config import Settings

BOT_TOKEN = "123:TEST"  # noqa: S105 - тестовый токен
PUBLIC_BASE_URL = "https://lms.example.com"
TEACHER_URL = "https://t.me/teacher"
_NOW = int(datetime(2026, 10, 6, 12, 0, tzinfo=UTC).timestamp())


class FakeTelegramSession(BaseSession):
    """Сессия aiogram без сети: записывает вызовы методов и возвращает заглушки."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError
        yield b""

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 - сигнатура задана aiogram
    ) -> TelegramType:
        del bot, timeout
        self.calls.append(method)
        name = type(method).__name__
        if name == "SendMessage":
            chat_id = cast(int, getattr(method, "chat_id", 0))
            payload = {
                "message_id": len(self.calls),
                "date": _NOW,
                "chat": {"id": chat_id, "type": "private"},
                "text": getattr(method, "text", ""),
            }
            return cast(TelegramType, method.__returning__.model_validate(payload))
        return cast(TelegramType, True)

    def of(self, name: str) -> list[TelegramMethod[Any]]:
        """Вызовы методов с указанным именем класса."""
        return [call for call in self.calls if type(call).__name__ == name]

    def sent_texts(self) -> list[str]:
        """Тексты всех отправленных сообщений."""
        return [str(getattr(call, "text", "")) for call in self.of("SendMessage")]


@dataclass
class BotHarness:
    """Бот + диспетчер + журнал вызовов Telegram."""

    bot: Bot
    dispatcher: Dispatcher
    session: FakeTelegramSession
    _update_id: int = field(default=0)

    def _next_id(self) -> int:
        self._update_id += 1
        return self._update_id

    @staticmethod
    def _from(telegram_id: int, username: str | None) -> dict[str, Any]:
        user: dict[str, Any] = {"id": telegram_id, "is_bot": False, "first_name": "Тест"}
        if username:
            user["username"] = username
        return user

    async def send_text(self, telegram_id: int, text: str, username: str | None = None) -> None:
        """Прислать боту текстовое сообщение (команда определяется по тексту)."""
        message: dict[str, Any] = {
            "message_id": self._next_id(),
            "date": _NOW,
            "chat": {"id": telegram_id, "type": "private"},
            "from": self._from(telegram_id, username),
            "text": text,
        }
        if text.startswith("/"):
            command = text.split()[0]
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(command)}]
        await self._feed({"update_id": self._next_id(), "message": message})

    async def press(self, telegram_id: int, data: str) -> None:
        """Нажать инлайн-кнопку с ``callback_data``."""
        callback = {
            "id": str(self._next_id()),
            "from": self._from(telegram_id, None),
            "chat_instance": "ci",
            "data": data,
            "message": {
                "message_id": self._next_id(),
                "date": _NOW,
                "chat": {"id": telegram_id, "type": "private"},
                "text": "prev",
            },
        }
        await self._feed({"update_id": self._next_id(), "callback_query": callback})

    async def chat_member(self, telegram_id: int, status: str) -> None:
        """Прислать ``my_chat_member`` с новым статусом бота в чате."""
        member = {
            "chat": {"id": telegram_id, "type": "private"},
            "from": self._from(telegram_id, None),
            "date": _NOW,
            "old_chat_member": {
                "status": "member",
                "user": {"id": 1, "is_bot": True, "first_name": "B"},
            },
            "new_chat_member": {
                "status": status,
                "user": {"id": 1, "is_bot": True, "first_name": "B"},
                # Для статуса kicked Telegram присылает until_date (0 — бессрочно).
                **({"until_date": 0} if status == "kicked" else {}),
            },
        }
        await self._feed({"update_id": self._next_id(), "my_chat_member": member})

    async def _feed(self, payload: dict[str, Any]) -> None:
        update = Update.model_validate(payload, context={"bot": self.bot})
        await self.dispatcher.feed_update(self.bot, update)


def make_settings(**overrides: object) -> Settings:
    """Настройки для тестов бота без чтения окружения."""
    values: dict[str, object] = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "DEFAULT_TIMEZONE": "UTC",
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "TEACHER_CONTACT_URL": TEACHER_URL,
        "BOT_TOKEN": SecretStr(BOT_TOKEN),
        "SENTRY_DSN": SecretStr(""),
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture
async def redis_clean(redis_client: aioredis.Redis) -> aioredis.Redis:
    """Redis без чужих ключей."""
    await redis_client.flushdb()
    return redis_client


@pytest.fixture
async def harness(db_session: AsyncSession, redis_clean: aioredis.Redis) -> BotHarness:
    """Бот с подменённым Telegram и общей тестовой сессией БД."""
    session = FakeTelegramSession()
    bot = Bot(token=BOT_TOKEN, session=session)

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    dispatcher = create_dispatcher(make_settings(), redis_clean, scope, storage=MemoryStorage())
    return BotHarness(bot=bot, dispatcher=dispatcher, session=session)
