"""Общая инфраструктура тестов бэкенда (T0.09).

Здесь живут фикстуры Testcontainers для PostgreSQL 16 и Redis 7, а также
готовые async-подключения к ним (SQLAlchemy async + asyncpg, redis.asyncio).

Важно: контейнеры поднимаются в Docker и полностью изолированы от локальных
PostgreSQL/Redis на машине разработчика — тесты работают независимо от того,
запущены ли локальные сервисы и на каких портах они сидят.

Модели SQLAlchemy и миграции здесь НЕ создаются — это задачи T0.10+.
Комментарии на русском согласно docs/06_agent_rules.md.
"""

from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

# Фиксируем версии образов под стек проекта (docs/02 §2.3): PostgreSQL 16+, Redis 7.
# Теги должны совпадать с docker-compose.yml, чтобы тесты гонялись на тех же версиях СУБД.
POSTGRES_IMAGE = "postgres:16"
REDIS_IMAGE = "redis:7"

# Тестовая БД: имя базы задаём своё, чтобы не зависеть от дефолтов образа.
TEST_DB_NAME = "lms_test"


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Поднимает контейнер PostgreSQL 16 на всю сессию тестов.

    Yields:
        Запущенный контейнер; доступ к строке подключения — через
        `get_connection_url()` (jdbc-формат) или поля хоста/порта.
    """
    with PostgresContainer(
        image=POSTGRES_IMAGE,
        username="test",
        password="test",
        dbname=TEST_DB_NAME,
    ) as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """Поднимает контейнер Redis 7 на всю сессию тестов.

    Yields:
        Запущенный контейнер; реальный (проброшенный на хост) порт доступен
        через `get_exposed_port(6379)`.
    """
    with RedisContainer(image=REDIS_IMAGE) as redis:
        yield redis


@pytest.fixture(scope="session")
def postgres_url(postgres_container: PostgresContainer) -> str:
    """Строка подключения PostgreSQL в asyncpg-формате (`postgresql+asyncpg://`).

    Возвращаемый адрес всегда указывает на контейнер (хост + проброшенный порт),
    поэтому локальный PostgreSQL тестам не мешает и не нужен.
    """
    # get_connection_url() отдаёт jdbc-URL вида
    # postgresql://user:pass@host:port/db?driver=... — пересобираем под asyncpg.
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return f"postgresql+asyncpg://test:test@{host}:{port}/{TEST_DB_NAME}"


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    """Строка подключения Redis (`redis://`), указывающая на контейнер."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture
async def pg_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    """Async-движок SQLAlchemy (драйвер asyncpg) для integration-тестов.

    Движок создаётся на каждый тест и корректно закрывается после него;
    пул соединений небольшой — тестовому контейнеру этого достаточно.
    """
    engine = create_async_engine(postgres_url, pool_size=2, max_overflow=0)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def pg_connection(pg_engine: AsyncEngine) -> AsyncIterator[asyncpg.Connection]:
    """Сырое asyncpg-подключение к той же базе.

    Нужен до появления моделей/миграций (следующие задачи), чтобы проверять
    саму связность и писать низкоуровневые интеграционные тесты без ORM.
    """
    # asyncpg понимает только свой собственный DSN (без префикса движка SQLAlchemy).
    dsn = pg_engine.url.render_as_string(hide_password=False).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )
    conn = await asyncpg.connect(dsn)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    """Асинхронный клиент Redis (redis.asyncio) для integration-тестов.

    Подключение создается на каждый тест и закрывается после него.
    decode_responses=True — значения приходят как str, так удобнее ассертить.
    """
    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
