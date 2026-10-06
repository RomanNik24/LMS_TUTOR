"""Создание владельца по OWNER_TELEGRAM_ID: функция, скрипт и lifespan (T1.09)."""

import importlib.util
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import redis.asyncio as aioredis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.api import deps
from src.core import config as config_module
from src.core.config import Settings
from src.core.enums import UserRole
from src.db.models import User
from src.main import create_app
from src.services.bootstrap import ensure_owner_from_settings

OWNER_TG_ID = 880_000_001
ROOT = Path(__file__).resolve().parents[2]


def _settings(monkeypatch: pytest.MonkeyPatch, db_url: str, redis_url: str, owner: str) -> Settings:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("SENTRY_DSN", "")
    if owner:
        monkeypatch.setenv("OWNER_TELEGRAM_ID", owner)
    else:
        monkeypatch.delenv("OWNER_TELEGRAM_ID", raising=False)
    return Settings()


@pytest.fixture
async def clean_owners(
    migrated_postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Гарантирует, что в БД нет владельцев до и после теста (тест коммитит по-настоящему)."""
    engine = create_async_engine(migrated_postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _wipe() -> None:
        async with factory() as session:
            await session.execute(delete(User).where(User.role == UserRole.OWNER))
            await session.commit()

    await _wipe()
    try:
        yield factory
    finally:
        await _wipe()
        await engine.dispose()


async def _owner_count(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as session:
        value = await session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.OWNER)
        )
    return int(value or 0)


async def test_owner_created_once_and_idempotent(
    clean_owners: async_sessionmaker[AsyncSession],
    migrated_postgres_url: str,
    redis_url: str,
    redis_client: aioredis.Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch, migrated_postgres_url, redis_url, str(OWNER_TG_ID))
    assert await ensure_owner_from_settings(settings, clean_owners, redis_client) is True
    assert await ensure_owner_from_settings(settings, clean_owners, redis_client) is False
    assert await _owner_count(clean_owners) == 1
    async with clean_owners() as session:
        owner = (
            await session.execute(select(User).where(User.role == UserRole.OWNER))
        ).scalar_one()
    assert owner.telegram_id == OWNER_TG_ID
    assert owner.display_name == "Владелец"


async def test_no_owner_id_creates_nothing(
    clean_owners: async_sessionmaker[AsyncSession],
    migrated_postgres_url: str,
    redis_url: str,
    redis_client: aioredis.Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch, migrated_postgres_url, redis_url, "")
    assert await ensure_owner_from_settings(settings, clean_owners, redis_client) is False
    assert await _owner_count(clean_owners) == 0


async def test_create_owner_script_is_idempotent(
    clean_owners: async_sessionmaker[AsyncSession],
    migrated_postgres_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location("create_owner", ROOT / "scripts/create_owner.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    settings = _settings(monkeypatch, migrated_postgres_url, redis_url, str(OWNER_TG_ID))
    assert await module.run(settings) is True
    assert await module.run(settings) is False
    assert await _owner_count(clean_owners) == 1


async def test_lifespan_creates_owner(
    clean_owners: async_sessionmaker[AsyncSession],
    migrated_postgres_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings(monkeypatch, migrated_postgres_url, redis_url, str(OWNER_TG_ID))
    for cached in (config_module.get_settings, deps.get_engine, deps.get_session_factory):
        cached.cache_clear()
    app = create_app("local")
    try:
        async with app.router.lifespan_context(app):
            assert await _owner_count(clean_owners) == 1
        async with app.router.lifespan_context(app):  # повторный старт — без дублей
            assert await _owner_count(clean_owners) == 1
    finally:
        for cached in (config_module.get_settings, deps.get_engine, deps.get_session_factory):
            cached.cache_clear()
