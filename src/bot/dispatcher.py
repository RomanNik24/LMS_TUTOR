"""Сборка ``Dispatcher`` бота (задача T1.11, docs/05).

FSM хранится в Redis с TTL 1 час. Middleware: сессия БД + ``AuthService``,
затем определение пользователя. Глобальный обработчик ошибок логирует
исключение (Sentry подхватывает ``ERROR``-логи) и отвечает нейтрально.
"""

import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent
from redis.asyncio import Redis

from src.bot.handlers import membership, menu, start
from src.bot.middlewares import AuthMiddleware, DbSessionMiddleware, SessionScope
from src.core import texts
from src.core.config import Settings
from src.core.constants import BOT_FSM_TTL_SECONDS

logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> bool:
    """Глобальный обработчик ошибок: лог с трейсбеком и нейтральный ответ.

    Персональные данные в лог не пишутся: только тип апдейта и исключение.
    """
    logger.error("Необработанная ошибка в обработчике бота", exc_info=event.exception)
    update = event.update
    if update.message is not None:
        await update.message.answer(texts.BOT_ERROR_GENERIC)
    elif update.callback_query is not None:
        await update.callback_query.answer(texts.BOT_ERROR_GENERIC)
    return True


def create_dispatcher(
    settings: Settings,
    redis: Redis,
    scope: SessionScope,
    storage: BaseStorage | None = None,
) -> Dispatcher:
    """Собрать ``Dispatcher`` с middleware, роутерами и обработчиком ошибок.

    Args:
        settings: Настройки приложения (доступны хэндлерам как ``settings``).
        redis: Клиент Redis (FSM и ``AuthService``).
        scope: Фабрика контекста сессии БД.
        storage: Хранилище FSM; по умолчанию Redis с TTL 1 час (в тестах — подмена).

    Returns:
        Готовый ``Dispatcher``.
    """
    fsm_storage = storage or RedisStorage(
        redis, state_ttl=BOT_FSM_TTL_SECONDS, data_ttl=BOT_FSM_TTL_SECONDS
    )
    dispatcher = Dispatcher(storage=fsm_storage, settings=settings)
    bot_token = settings.bot_token.get_secret_value()
    dispatcher.update.outer_middleware(
        DbSessionMiddleware(scope, redis, bot_token, settings.session_secret.get_secret_value())
    )
    dispatcher.update.outer_middleware(AuthMiddleware())
    dispatcher.errors.register(on_error)
    # Порядок важен: menu содержит универсальный fallback и идёт последним.
    dispatcher.include_router(membership.create_router())
    dispatcher.include_router(start.create_router())
    dispatcher.include_router(menu.create_router())
    return dispatcher
