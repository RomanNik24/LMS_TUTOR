"""Минимальный smoke-тест инфраструктуры backend-тестов (T0.09).

Доказывает, что Testcontainers-фикстуры из tests/conftest.py работают:
- контейнер PostgreSQL 16 стартует и принимает asyncpg/SQLAlchemy-подключение;
- контейнер Redis 7 стартует и отвечает PING -> True.

Тест не зависит от локальных PostgreSQL/Redis: подключения всегда указывают
на свежесозданные контейнеры с проброшенными на хост случайными портами.
"""

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_postgres_container_accepts_connection(pg_engine: AsyncEngine) -> None:
    """PostgreSQL-контейнер поднят, SQLAlchemy async (asyncpg) подключается к нему."""
    async with pg_engine.connect() as conn:
        server_version = await conn.scalar(text("SELECT version()"))
        one = await conn.scalar(text("SELECT 1"))

    # SELECT 1 проходит только при живом соединении с сервером в контейнере.
    assert one == 1
    # Сервер должен быть PostgreSQL нужной мажорной версии (стек проекта — 16).
    assert server_version is not None
    assert "PostgreSQL" in str(server_version)
    assert str(server_version).split()[1].startswith("16")


async def test_redis_container_answers_ping(redis_client: aioredis.Redis) -> None:
    """Redis-контейнер поднят и отвечает на PING."""
    pong = await redis_client.ping()

    # redis.asyncio возвращает True при успешном PING.
    assert pong is True
