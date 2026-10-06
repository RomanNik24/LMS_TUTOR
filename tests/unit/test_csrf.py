"""Тесты CSRF-middleware T1.08 (docs/09 §2.3.1): Origin и X-Requested-With."""

import httpx
import pytest
from fastapi import FastAPI
from src.core.csrf import CsrfMiddleware, origin_of
from src.core.error_handlers import register_error_handlers

pytestmark = pytest.mark.security

BASE = "https://lms.example.com"
OK_HEADERS = {"Origin": BASE, "X-Requested-With": "XMLHttpRequest"}


def _app(base_url: str = BASE) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(CsrfMiddleware, public_base_url=lambda: base_url)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/thing")
    @app.patch("/api/v1/thing")
    @app.put("/api/v1/thing")
    @app.delete("/api/v1/thing")
    async def thing() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/telegram/webhook")
    async def webhook() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://test"
    ) as c:
        yield c


def test_origin_of() -> None:
    assert origin_of("https://Lms.Example.com/path?x=1") == "https://lms.example.com"
    assert origin_of("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert origin_of("") == ""
    assert origin_of("not a url") == ""


async def test_get_is_not_checked(client: httpx.AsyncClient) -> None:
    assert (await client.get("/ping")).status_code == 200


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
async def test_valid_unsafe_request_passes(client: httpx.AsyncClient, method: str) -> None:
    response = await client.request(method, "/api/v1/thing", headers=OK_HEADERS)
    assert response.status_code == 200


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
async def test_missing_x_requested_with_is_403(client: httpx.AsyncClient, method: str) -> None:
    response = await client.request(method, "/api/v1/thing", headers={"Origin": BASE})
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "permission_denied"
    assert body["details"] == {"reason": "csrf_header"}


async def test_wrong_header_value_is_403(client: httpx.AsyncClient) -> None:
    headers = {"Origin": BASE, "X-Requested-With": "fetch"}
    assert (await client.post("/api/v1/thing", headers=headers)).status_code == 403


async def test_missing_origin_is_403(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/thing", headers={"X-Requested-With": "XMLHttpRequest"})
    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"reason": "csrf_origin"}


async def test_foreign_origin_is_403(client: httpx.AsyncClient) -> None:
    headers = {"Origin": "https://evil.example.com", "X-Requested-With": "XMLHttpRequest"}
    assert (await client.post("/api/v1/thing", headers=headers)).status_code == 403


async def test_telegram_webhook_is_exempt(client: httpx.AsyncClient) -> None:
    assert (await client.post("/telegram/webhook")).status_code == 200


async def test_unset_public_base_url_fails_closed() -> None:
    transport = httpx.ASGITransport(app=_app(base_url=""))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.post("/api/v1/thing", headers=OK_HEADERS)
    assert response.status_code == 403
