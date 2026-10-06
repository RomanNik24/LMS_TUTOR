"""Тесты проверки живости приложения и загрузки конфигурации."""

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport
from pydantic import ValidationError
from src.api.deps import get_redis, get_session
from src.core.config import Settings
from src.main import app

# Тестовый адрес: запросы идут напрямую в ASGI-приложение, сеть не нужна.
TEST_BASE_URL = "http://testserver"

# Значения-заглушки для обязательных настроек. Реальные секреты не нужны.
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/lms"
TEST_REDIS_URL = "redis://localhost:6379/0"
TEST_TIMEZONE = "Europe/Moscow"


class _FakeSession:
    """Подмена AsyncSession: ``execute`` либо работает, либо падает."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def execute(self, statement: object) -> None:
        del statement
        if self._fail:
            raise ConnectionError("db down")


class _FakeRedis:
    """Подмена Redis: ``ping`` либо работает, либо падает."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def ping(self) -> bool:
        if self._fail:
            raise ConnectionError("redis down")
        return True


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """HTTP-клиент, работающий с приложением в памяти (БД и Redis подменяются в тесте)."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(base_url=TEST_BASE_URL, transport=transport) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _override(*, db_fail: bool = False, redis_fail: bool = False) -> None:
    async def _session() -> AsyncIterator[_FakeSession]:
        yield _FakeSession(fail=db_fail)

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_redis] = lambda: _FakeRedis(fail=redis_fail)


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    """`GET /health` при живых БД и Redis: 200 и `status=ok`."""
    _override()
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}


async def test_health_degrades_when_redis_is_down(client: httpx.AsyncClient) -> None:
    """Redis недоступен → 503 `degraded`, БД при этом `ok`."""
    _override(redis_fail=True)
    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "ok", "redis": "error"}


async def test_health_degrades_when_database_is_down(client: httpx.AsyncClient) -> None:
    """БД недоступна → 503 `degraded`."""
    _override(db_fail=True)
    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "error", "redis": "ok"}


def test_settings_fail_in_prod_with_empty_session_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """При `APP_ENV=prod` и пустом `SESSION_SECRET` настройки не собираются."""
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("REDIS_URL", TEST_REDIS_URL)
    monkeypatch.setenv("DEFAULT_TIMEZONE", TEST_TIMEZONE)
    monkeypatch.setenv("SESSION_SECRET", "")

    with pytest.raises(ValidationError):
        Settings()
