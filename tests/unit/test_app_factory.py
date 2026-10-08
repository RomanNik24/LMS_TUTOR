"""Тесты сборки приложения T1.08: /docs в prod, CORS, request_id, Sentry."""

import httpx
import pytest
from sentry_sdk.types import Event
from src.core.config import Settings
from src.core.sentry import init_sentry, scrub_event
from src.main import create_app

pytestmark = pytest.mark.security

CORS_ORIGIN = "http://localhost:5173"


async def _get(app_env: str, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(app_env))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_closed_in_prod(path: str) -> None:
    response = await _get("prod", path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
async def test_docs_open_in_local(path: str) -> None:
    assert (await _get("local", path)).status_code == 200


async def test_cors_only_in_local() -> None:
    headers = {"Origin": CORS_ORIGIN}
    local = await _get("local", "/openapi.json", headers)
    prod = await _get("staging", "/openapi.json", headers)
    assert local.headers.get("access-control-allow-origin") == CORS_ORIGIN
    assert "access-control-allow-origin" not in prod.headers


async def test_csrf_rejection_carries_request_id() -> None:
    transport = httpx.ASGITransport(app=create_app("local"))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/anything", headers={"X-Request-ID": "rid-123"})
    assert response.status_code == 403
    assert response.headers["x-request-id"] == "rid-123"


def _settings(monkeypatch: pytest.MonkeyPatch, *, app_env: str, dsn: str) -> Settings:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("SENTRY_DSN", dsn)
    if app_env == "prod":
        monkeypatch.setenv("BOT_TOKEN", "123:TEST")
        monkeypatch.setenv("WEBHOOK_SECRET", "w")
        monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    return Settings()


def test_sentry_disabled_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    assert init_sentry(_settings(monkeypatch, app_env="staging", dsn="")) is False


def test_sentry_disabled_in_local_even_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = "https://key@o0.ingest.sentry.io/1"
    assert init_sentry(_settings(monkeypatch, app_env="local", dsn=dsn)) is False


def test_scrub_event_removes_sensitive_data() -> None:
    event: Event = {
        "request": {
            "data": {"init_data": "secret"},
            "cookies": {"session_id": "abc"},
            "query_string": "tgWebAppData=secret",
            "url": "https://x.example/telegram/webhook/abcdef0123456789",
            "headers": {"Cookie": "session_id=abc", "X-Request-ID": "r1", "Authorization": "x"},
        },
        "user": {"id": 1},
    }
    scrubbed = scrub_event(event, {})
    assert scrubbed is not None
    assert scrubbed["request"] == {
        "url": "https://x.example/telegram/webhook/***",
        "headers": {"X-Request-ID": "r1"},
    }
    assert "user" not in scrubbed


async def test_api_responses_carry_security_headers() -> None:
    """T8.08: единый набор заголовков и без кэша для данных API (в том числе у ошибок)."""
    api = await _get("local", "/api/v1/unknown")
    other = await _get("local", "/openapi.json")

    assert api.status_code == 404  # заголовки есть и у ответа с ошибкой
    for response in (api, other):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
    assert api.headers["cache-control"] == "no-store"
    assert "cache-control" not in other.headers
