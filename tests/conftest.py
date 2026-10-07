"""Общая инфраструктура тестов бэкенда (T0.09).

Здесь живут фикстуры Testcontainers для PostgreSQL 16 и Redis 7, а также
готовые async-подключения к ним (SQLAlchemy async + asyncpg, redis.asyncio).

Важно: контейнеры поднимаются в Docker и полностью изолированы от локальных
PostgreSQL/Redis на машине разработчика — тесты работают независимо от того,
запущены ли локальные сервисы и на каких портах они сидят.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

import os
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import asyncpg
import httpx
import pytest
import redis.asyncio as aioredis
import time_machine
from alembic import command as alembic_command
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

# Фиксируем версии образов под стек проекта (docs/02 §2.3): PostgreSQL 16+, Redis 7.
# Теги должны совпадать с docker-compose.yml, чтобы тесты гонялись на тех же версиях СУБД.
POSTGRES_IMAGE = "postgres:16"
REDIS_IMAGE = "redis:7"

# Тестовая БД: имя базы задаём своё, чтобы не зависеть от дефолтов образа.
TEST_DB_NAME = "lms_test"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Автоматически помечает всё из tests/integration маркером `integration`."""
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


def _use_services() -> bool:
    """True, если адреса PostgreSQL/Redis заданы окружением (CI), а не Testcontainers."""
    return os.environ.get("TEST_USE_SERVICES") == "1"


def _required_env(name: str) -> str:
    """Вернуть обязательную переменную окружения режима TEST_USE_SERVICES=1."""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"TEST_USE_SERVICES=1, но переменная {name} не задана")
    return value


ContainerT = TypeVar("ContainerT", PostgresContainer, RedisContainer)


def _start_or_skip(create: Callable[[], ContainerT]) -> ContainerT:
    """Создать и запустить контейнер; без Docker интеграционные тесты пропускаются.

    Клиент Docker создаётся уже в конструкторе контейнера, поэтому в ``try`` — оба шага.
    В CI (TEST_USE_SERVICES=1) контейнеры не нужны, поэтому тихого пропуска там не бывает.
    """
    try:
        container = create()
        container.start()
        return container
    except DockerException as error:
        pytest.skip(f"Docker недоступен ({type(error).__name__}): интеграционные тесты пропущены")


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Поднимает контейнер PostgreSQL 16 на всю сессию тестов.

    Используется только без TEST_USE_SERVICES=1; в CI адрес берётся из окружения.
    """
    postgres = _start_or_skip(
        lambda: PostgresContainer(
            image=POSTGRES_IMAGE,
            username="test",
            password="test",  # noqa: S106
            dbname=TEST_DB_NAME,
        )
    )
    try:
        yield postgres
    finally:
        postgres.stop()


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """Поднимает контейнер Redis 7 на всю сессию тестов (без TEST_USE_SERVICES=1)."""
    redis = _start_or_skip(lambda: RedisContainer(image=REDIS_IMAGE))
    try:
        yield redis
    finally:
        redis.stop()


@pytest.fixture(scope="session")
def postgres_url(request: pytest.FixtureRequest) -> str:
    """Строка подключения PostgreSQL в asyncpg-формате (`postgresql+asyncpg://`).

    TEST_USE_SERVICES=1 → берётся `DATABASE_URL_TEST` (service container CI);
    иначе — свежий контейнер Testcontainers (локальный PostgreSQL не нужен).
    """
    if _use_services():
        return _required_env("DATABASE_URL_TEST")
    container: PostgresContainer = request.getfixturevalue("postgres_container")
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return f"postgresql+asyncpg://test:test@{host}:{port}/{TEST_DB_NAME}"


@pytest.fixture(scope="session")
def redis_url(request: pytest.FixtureRequest) -> str:
    """Строка подключения Redis: `REDIS_URL_TEST` (CI) или контейнер Testcontainers."""
    if _use_services():
        return _required_env("REDIS_URL_TEST")
    container: RedisContainer = request.getfixturevalue("redis_container")
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
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


ROOT = Path(__file__).resolve().parents[1]


def _alembic_upgrade_head(database_url: str) -> None:
    """Применить миграции в отдельном потоке (env.py запускает свой event loop)."""

    def _command() -> None:
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            cfg = Config(str(ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(ROOT / "src/db/migrations"))
            alembic_command.upgrade(cfg, "head")
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_command).result()


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_url: str) -> str:
    """PostgreSQL со схемой `alembic upgrade head` (один раз на сессию тестов)."""
    _alembic_upgrade_head(postgres_url)
    return postgres_url


@pytest.fixture
async def db_session(migrated_postgres_url: str) -> AsyncIterator[AsyncSession]:
    """Асинхронная сессия SQLAlchemy с откатом после теста.

    Сессия работает внутри внешней транзакции соединения; `commit()` внутри
    теста превращается в SAVEPOINT, а по завершении теста всё откатывается —
    тесты не влияют друг на друга.
    """
    engine = create_async_engine(migrated_postgres_url, pool_size=2, max_overflow=0)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            session = AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                yield session
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    """`httpx.AsyncClient`, подключённый напрямую к FastAPI-приложению (без сети)."""
    from src.main import app  # noqa: PLC0415 - импорт приложения только при необходимости

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def frozen_time() -> Iterator[time_machine.travel]:
    """Фикстура time-machine: `frozen_time.move_to(...)` двигает время в тесте.

    Старт — фиксированный момент в UTC; тики выключены, время идёт только по команде.
    """
    with time_machine.travel(datetime(2026, 10, 6, 12, 0, tzinfo=UTC), tick=False) as traveller:
        yield traveller
