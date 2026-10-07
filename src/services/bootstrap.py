"""Создание первого владельца по ``OWNER_TELEGRAM_ID`` (docs/05 §3.2).

Используется при старте приложения (lifespan) и скриптом
``scripts/create_owner.py``. Идемпотентно: если владелец уже есть или
``OWNER_TELEGRAM_ID`` не задан, ничего не создаётся.
"""

import logging

from redis.asyncio import Redis

from src.core.config import Settings
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.session import SessionFactory, session_scope
from src.services.auth import AuthService

logger = logging.getLogger(__name__)


async def ensure_owner_from_settings(
    settings: Settings, factory: SessionFactory, redis: Redis
) -> bool:
    """Создать владельца, если задан ``OWNER_TELEGRAM_ID`` и владельца ещё нет.

    Args:
        settings: Настройки приложения.
        factory: Фабрика сессий БД.
        redis: Клиент Redis (нужен конструктору ``AuthService``).

    Returns:
        ``True``, если владелец создан именно сейчас.
    """
    if settings.owner_telegram_id is None:
        return False
    async with session_scope(factory) as session:
        service = AuthService(
            session,
            SessionStore(redis, settings.session_secret.get_secret_value()),
            RateLimiter(redis),
        )
        had_owner = await service.has_owner()
        await service.ensure_owner(settings.owner_telegram_id)
    if not had_owner:
        logger.info("Создан первый владелец по OWNER_TELEGRAM_ID")
    return not had_owner
