"""Тесты rate limit T1.08 (docs/08 §10): /auth/* по IP и остальное по пользователю."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
import pytest
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.api.deps import current_user, get_redis, get_session, rate_limit_auth
from src.core.constants import RATE_LIMIT_AUTH_PER_MINUTE, SESSION_COOKIE_NAME
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.error_handlers import register_error_handlers
from src.core.exceptions import AppError
from src.core.rate_limit import RateLimiter
from src.core.session_store import SessionStore
from src.db.models import User
from src.repositories.users import UserRepository

pytestmark = pytest.mark.security


@pytest.fixture
async def client(
    db_session: AsyncSession, redis_client: aioredis.Redis
) -> AsyncIterator[httpx.AsyncClient]:
    await redis_client.flushdb()
    app = FastAPI()
    register_error_handlers(app)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_redis] = lambda: redis_client

    @app.post("/auth/telegram", dependencies=[Depends(rate_limit_auth)])
    async def auth() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/me")
    async def me(user: Annotated[CurrentUser, Depends(current_user)]) -> dict[str, int]:
        return {"id": user.id}

    transport = httpx.ASGITransport(app=app, client=("203.0.113.5", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_auth_limit_is_10_per_minute_per_ip(client: httpx.AsyncClient) -> None:
    for _ in range(RATE_LIMIT_AUTH_PER_MINUTE):
        assert (await client.post("/auth/telegram")).status_code == 200
    response = await client.post("/auth/telegram")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


async def test_user_limit_applies_per_user(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    redis_client: aioredis.Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps, "RATE_LIMIT_USER_PER_MINUTE", 3)
    repo = UserRepository(db_session)
    first = await repo.add(User(role=UserRole.STUDENT, display_name="a"))
    second = await repo.add(User(role=UserRole.STUDENT, display_name="b"))
    store = SessionStore(redis_client)
    a_id, _ = await store.create(first.id, first.role)
    b_id, _ = await store.create(second.id, second.role)
    a_headers = {"Cookie": f"{SESSION_COOKIE_NAME}={a_id}"}
    b_headers = {"Cookie": f"{SESSION_COOKIE_NAME}={b_id}"}

    for _ in range(3):
        assert (await client.get("/me", headers=a_headers)).status_code == 200
    blocked = await client.get("/me", headers=a_headers)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    # Другой пользователь не затронут.
    assert (await client.get("/me", headers=b_headers)).status_code == 200


async def test_window_resets_after_expiry(redis_client: aioredis.Redis) -> None:
    await redis_client.flushdb()
    limiter = RateLimiter(redis_client)
    await limiter.hit("t", "x", 1)
    with pytest.raises(AppError, match="Слишком много"):
        await limiter.hit("t", "x", 1)
    await redis_client.delete("rate:t:x")  # окно истекло
    await limiter.hit("t", "x", 1)


async def test_window_has_ttl(redis_client: aioredis.Redis) -> None:
    await redis_client.flushdb()
    await RateLimiter(redis_client).hit("t", "y", 5)
    assert 0 < await redis_client.ttl("rate:t:y") <= 60
