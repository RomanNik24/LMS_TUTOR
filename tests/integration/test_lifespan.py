"""Lifespan T1.08: клиент Redis создаётся при старте и закрывается при остановке."""

import pytest
import redis.asyncio as aioredis
from src.core import config as config_module
from src.main import create_app


async def test_lifespan_creates_and_closes_redis(
    redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("SENTRY_DSN", "")
    config_module.get_settings.cache_clear()
    closed: list[bool] = []
    original_aclose = aioredis.Redis.aclose

    async def _spy(self: aioredis.Redis, close_connection_pool: bool | None = None) -> None:
        closed.append(True)
        await original_aclose(self, close_connection_pool)

    monkeypatch.setattr(aioredis.Redis, "aclose", _spy)
    app = create_app("local")
    try:
        async with app.router.lifespan_context(app):
            redis: aioredis.Redis = app.state.redis
            assert await redis.ping() is True
            assert closed == []
        assert closed == [True]
    finally:
        config_module.get_settings.cache_clear()
