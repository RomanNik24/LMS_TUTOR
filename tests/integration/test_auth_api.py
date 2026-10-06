"""Интеграционные тесты REST /auth/* и /me (T1.10): коды 200/204/401/403/404/409/422/429."""

import hashlib
import hmac
import json
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
import redis.asyncio as aioredis
import time_machine
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.core import config as config_module
from src.core.constants import RATE_LIMIT_AUTH_PER_MINUTE, SESSION_COOKIE_NAME
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.models import User
from src.main import create_app
from src.services.auth import AuthService

pytestmark = pytest.mark.security

BASE = "https://lms.example.com"
BOT_TOKEN = "123:TEST"  # noqa: S105 - тестовый токен
ROOT = Path(__file__).resolve().parents[2]
CSRF = {"Origin": BASE, "X-Requested-With": "XMLHttpRequest"}


def _init_data(telegram_id: int, *, age_seconds: int = 0, token: str = BOT_TOKEN) -> str:
    user = json.dumps({"id": telegram_id, "first_name": "Аня", "username": "anya"})
    fields = {"auth_date": str(int(time.time()) - age_seconds), "user": user, "query_id": "AAH"}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


@pytest.fixture
async def redis_clean(redis_client: aioredis.Redis) -> aioredis.Redis:
    await redis_client.flushdb()
    return redis_client


@pytest.fixture
def app(
    db_session: AsyncSession, redis_clean: aioredis.Redis, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("SENTRY_DSN", "")
    config_module.get_settings.cache_clear()
    application = create_app("local")

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[deps.get_session] = _session
    application.dependency_overrides[deps.get_redis] = lambda: redis_clean
    yield application
    config_module.get_settings.cache_clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=("198.51.100.7", 4000))
    async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=CSRF) as c:
        yield c


async def _user(
    db: AsyncSession,
    role: UserRole = UserRole.STUDENT,
    *,
    telegram_id: int | None = None,
    active: bool = True,
    name: str = "Аня",
) -> User:
    user = User(role=role, display_name=name, telegram_id=telegram_id, is_active=active)
    db.add(user)
    await db.commit()
    return user


def _cookie(client: httpx.AsyncClient) -> str:
    value = client.cookies.get(SESSION_COOKIE_NAME)
    assert value
    return value


# ---------------------------------------------------------------- POST /auth/telegram


async def test_telegram_login_sets_cookie_and_returns_me(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await _user(db_session, telegram_id=7001)
    response = await client.post("/api/v1/auth/telegram", json={"init_data": _init_data(7001)})
    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "role": "student",
        "display_name": "Аня",
        "timezone": "Europe/Moscow",
    }
    header = response.headers["set-cookie"].lower()
    assert SESSION_COOKIE_NAME in header
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["id"] == user.id


async def test_telegram_login_forged_init_data_is_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _user(db_session, telegram_id=7002)
    forged = _init_data(7002, token="999:OTHER")  # noqa: S106 - подпись чужим токеном
    response = await client.post("/api/v1/auth/telegram", json={"init_data": forged})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert "set-cookie" not in response.headers


async def test_telegram_login_tampered_user_id_is_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _user(db_session, UserRole.OWNER, telegram_id=7003)
    await _user(db_session, telegram_id=7004)
    forged = _init_data(7004).replace("7004", "7003")  # подмена id на чужой (владельца)
    response = await client.post("/api/v1/auth/telegram", json={"init_data": forged})
    assert response.status_code == 401


async def test_telegram_login_expired_init_data_is_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _user(db_session, telegram_id=7005)
    stale = _init_data(7005, age_seconds=25 * 3600)
    response = await client.post("/api/v1/auth/telegram", json={"init_data": stale})
    assert response.status_code == 401


async def test_telegram_login_unknown_or_archived_user_is_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _user(db_session, telegram_id=7006, active=False)
    unknown = await client.post("/api/v1/auth/telegram", json={"init_data": _init_data(1)})
    archived = await client.post("/api/v1/auth/telegram", json={"init_data": _init_data(7006)})
    assert unknown.status_code == 401
    assert archived.status_code == 401


async def test_telegram_login_validation_error_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/auth/telegram", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    extra = await client.post("/api/v1/auth/telegram", json={"init_data": "x", "role": "owner"})
    assert extra.status_code == 422


async def test_auth_requires_csrf_headers_403(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as bare:
        response = await bare.post("/api/v1/auth/telegram", json={"init_data": "x"})
        foreign = await bare.post(
            "/api/v1/auth/telegram",
            json={"init_data": "x"},
            headers={"Origin": "https://evil.example", "X-Requested-With": "XMLHttpRequest"},
        )
    assert response.status_code == 403
    assert foreign.status_code == 403


async def test_auth_rate_limit_429(client: httpx.AsyncClient) -> None:
    for _ in range(RATE_LIMIT_AUTH_PER_MINUTE):
        assert (
            await client.post("/api/v1/auth/telegram", json={"init_data": "x"})
        ).status_code == 401
    response = await client.post("/api/v1/auth/telegram", json={"init_data": "x"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


# ---------------------------------------------------------------- POST /auth/link


async def _web_link(db: AsyncSession, redis: aioredis.Redis, user: User) -> str:
    service = AuthService(db, SessionStore(redis), RateLimiter(redis), BOT_TOKEN)
    issued = await service.create_web_login_link(
        CurrentUser(id=user.id, role=user.role, timezone=user.timezone)
    )
    return issued.token


async def test_link_login_works_once_then_409(
    client: httpx.AsyncClient, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    user = await _user(db_session, UserRole.MANAGER, telegram_id=7010, name="Менеджер")
    token = await _web_link(db_session, redis_clean, user)
    first = await client.post("/api/v1/auth/link", json={"token": token})
    assert first.status_code == 200
    assert first.json()["role"] == "manager"
    assert SESSION_COOKIE_NAME in first.headers["set-cookie"]
    again = await client.post("/api/v1/auth/link", json={"token": token})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invite_already_used"


async def test_link_login_unknown_token_404(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/auth/link", json={"token": "nope"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "login_link_invalid"


async def test_link_login_expired_token_404(
    client: httpx.AsyncClient, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    user = await _user(db_session, telegram_id=7011)
    token = await _web_link(db_session, redis_clean, user)
    later = datetime.now(UTC) + timedelta(minutes=11)
    with time_machine.travel(later, tick=False):
        response = await client.post("/api/v1/auth/link", json={"token": token})
    assert response.status_code == 404


async def test_link_get_is_not_allowed(client: httpx.AsyncClient) -> None:
    """Погашение только POST: GET по ссылке токен не сжигает (docs/09 §2.3)."""
    response = await client.get("/api/v1/auth/link")
    assert response.status_code == 405


# ---------------------------------------------------------------- logout, /me


async def test_logout_deletes_session_and_clears_cookie(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _user(db_session, telegram_id=7020)
    await client.post("/api/v1/auth/telegram", json={"init_data": _init_data(7020)})
    session_id = _cookie(client)
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    client.cookies.set(SESSION_COOKIE_NAME, session_id)  # старый cookie больше не работает
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_logout_and_me_require_session_401(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/logout")).status_code == 401
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await client.patch("/api/v1/me", json={"display_name": "X"})).status_code == 401


async def _login(client: httpx.AsyncClient, db: AsyncSession, tg: int) -> User:
    user = await _user(db, telegram_id=tg)
    await client.post("/api/v1/auth/telegram", json={"init_data": _init_data(tg)})
    return user


async def test_patch_me_updates_timezone_and_name(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _login(client, db_session, 7030)
    response = await client.patch(
        "/api/v1/me", json={"timezone": "Asia/Yekaterinburg", "display_name": "  Анна  "}
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Yekaterinburg"
    assert response.json()["display_name"] == "Анна"
    assert (await client.get("/api/v1/me")).json()["timezone"] == "Asia/Yekaterinburg"


@pytest.mark.parametrize(
    "payload",
    [
        {"timezone": "Mars/Phobos"},
        {"display_name": "   "},
        {"display_name": "я" * 151},
        {},
        {"role": "owner"},
        {"display_name": "Ок", "role": "owner"},
        {"id": 1},
    ],
)
async def test_patch_me_rejects_bad_payload_422(
    client: httpx.AsyncClient, db_session: AsyncSession, payload: dict[str, object]
) -> None:
    user = await _login(client, db_session, 7031)
    response = await client.patch("/api/v1/me", json=payload)
    assert response.status_code == 422
    await db_session.refresh(user)
    assert user.role == UserRole.STUDENT


async def test_me_response_has_no_private_fields(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _login(client, db_session, 7032)
    body = (await client.get("/api/v1/me")).json()
    assert set(body) == {"id", "role", "display_name", "timezone"}


# ---------------------------------------------------------------- OpenAPI


async def test_openapi_contains_paths_operation_ids_and_error_models(app: FastAPI) -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert "post" in paths["/api/v1/auth/telegram"]
    assert "post" in paths["/api/v1/auth/link"]
    assert "post" in paths["/api/v1/auth/logout"]
    assert {"get", "patch"} <= set(paths["/api/v1/me"])
    operation_ids = {
        op["operationId"] for item in paths.values() for op in item.values() if "operationId" in op
    }
    assert {
        "auth_telegram_login",
        "auth_link_login",
        "auth_logout",
        "get_me",
        "update_me",
    } <= operation_ids
    assert {"401", "422", "429"} <= set(paths["/api/v1/auth/telegram"]["post"]["responses"])
    assert {"404", "409"} <= set(paths["/api/v1/auth/link"]["post"]["responses"])
    assert "ErrorResponse" in schema["components"]["schemas"]


def test_export_openapi_script(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    result = subprocess.run(  # noqa: S603 - запуск собственного скрипта проекта
        [sys.executable, "-I", str(ROOT / "scripts/export_openapi.py"), str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    schema = json.loads(out.read_text(encoding="utf-8"))
    assert "/api/v1/auth/telegram" in schema["paths"]
    assert "/api/v1/me" in schema["paths"]
