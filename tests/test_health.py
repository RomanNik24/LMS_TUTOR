"""Тесты проверки живости приложения и загрузки конфигурации."""

import httpx
import pytest
from httpx import ASGITransport
from pydantic import ValidationError
from src.core.config import Settings
from src.main import app

# Тестовый адрес: запросы идут напрямую в ASGI-приложение, сеть не нужна.
TEST_BASE_URL = "http://testserver"

# Значения-заглушки для обязательных настроек. Реальные секреты не нужны.
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/lms"
TEST_REDIS_URL = "redis://localhost:6379/0"
TEST_TIMEZONE = "Europe/Moscow"


@pytest.fixture
async def client() -> httpx.AsyncClient:
    """HTTP-клиент, работающий с приложением в памяти.

    Yields:
        Клиент с базовым адресом тестового сервера.
    """
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(base_url=TEST_BASE_URL, transport=transport) as test_client:
        yield test_client


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    """`GET /health` отвечает 200 и возвращает `{"status": "ok"}`."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
