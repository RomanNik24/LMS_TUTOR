"""Тесты серверных сессий и зависимостей current_user/require_role (T1.08)."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
import pytest
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.cookies import clear_session_cookie, set_session_cookie
from src.api.deps import current_user, get_redis, get_session, require_role
from src.core.constants import SESSION_COOKIE_NAME
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.error_handlers import register_error_handlers
from src.core.session_store import SessionStore, session_ttl_seconds
from src.db.models import User
from src.repositories.users import UserRepository

pytestmark = pytest.mark.security

DAY = 24 * 60 * 60


def _cookie(session_id: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"}


def _build_app(db_session: AsyncSession, redis: aioredis.Redis) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_redis] = lambda: redis

    @app.get("/me")
    async def me(user: Annotated[CurrentUser, Depends(current_user)]) -> dict[str, object]:
        return {"id": user.id, "role": user.role.value, "timezone": user.timezone}

    @app.get("/staff")
    async def staff(
        user: Annotated[CurrentUser, Depends(require_role(UserRole.OWNER, UserRole.MANAGER))],
    ) -> dict[str, int]:
        return {"id": user.id}

    return app


@pytest.fixture
async def redis_clean(redis_client: aioredis.Redis) -> aioredis.Redis:
    await redis_client.flushdb()
    return redis_client


@pytest.fixture
async def client(
    db_session: AsyncSession, redis_clean: aioredis.Redis
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_build_app(db_session, redis_clean))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _user(db: AsyncSession, role: UserRole, *, is_active: bool = True) -> User:
    user = User(role=role, display_name=role.value, is_active=is_active)
    return await UserRepository(db).add(user)


async def test_ttl_by_role() -> None:
    assert session_ttl_seconds(UserRole.STUDENT) == 30 * DAY
    assert session_ttl_seconds(UserRole.MANAGER) == 7 * DAY
    assert session_ttl_seconds(UserRole.OWNER) == 7 * DAY


async def test_no_cookie_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_garbage_cookie_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/me", headers=_cookie("nope"))
    assert response.status_code == 401


async def test_valid_session_returns_current_user(
    client: httpx.AsyncClient, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    user = await _user(db_session, UserRole.STUDENT)
    session_id, ttl = await SessionStore(redis_clean).create(user.id, user.role)
    assert ttl == 30 * DAY
    response = await client.get("/me", headers=_cookie(session_id))
    assert response.status_code == 200
    assert response.json() == {"id": user.id, "role": "student", "timezone": "Europe/Moscow"}


async def test_expired_session_is_401(
    client: httpx.AsyncClient, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    user = await _user(db_session, UserRole.STUDENT)
    store = SessionStore(redis_clean)
    session_id, _ = await store.create(user.id, user.role)
    keys = [k async for k in redis_clean.scan_iter("session:*")]
    await redis_clean.pexpire(keys[0], 1)
    import asyncio

    await asyncio.sleep(0.05)
    response = await client.get("/me", headers=_cookie(session_id))
    assert response.status_code == 401


async def test_sliding_ttl_is_refreshed(
    client: httpx.AsyncClient, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    user = await _user(db_session, UserRole.MANAGER)
    session_id, _ = await SessionStore(redis_clean).create(user.id, user.role)
    key = [k async for k in redis_clean.scan_iter("session:*")][0]
    await redis_clean.expire(key, 100)
    assert await client.get("/me", headers=_cookie(session_id))
    assert await redis_clean.ttl(key) > 6 * DAY


async def test_archived_user_is_rejected_and_sessions_removed(
    client: httpx.AsyncClient, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    user = await _user(db_session, UserRole.STUDENT, is_active=False)
    store = SessionStore(redis_clean)
    first, _ = await store.create(user.id, user.role)
    second, _ = await store.create(user.id, user.role)
    response = await client.get("/me", headers=_cookie(first))
    assert response.status_code == 401
    assert await store.get(second) is None  # все сессии пользователя удалены


async def test_session_of_missing_user_is_401(
    client: httpx.AsyncClient, redis_clean: aioredis.Redis
) -> None:
    session_id, _ = await SessionStore(redis_clean).create(999_999_999, UserRole.STUDENT)
    response = await client.get("/me", headers=_cookie(session_id))
    assert response.status_code == 401


async def test_require_role(
    client: httpx.AsyncClient, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> None:
    store = SessionStore(redis_clean)
    student = await _user(db_session, UserRole.STUDENT)
    manager = await _user(db_session, UserRole.MANAGER)
    s_id, _ = await store.create(student.id, student.role)
    m_id, _ = await store.create(manager.id, manager.role)
    denied = await client.get("/staff", headers=_cookie(s_id))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"
    assert (await client.get("/staff", headers=_cookie(m_id))).status_code == 200
    assert (await client.get("/staff")).status_code == 401


async def test_delete_removes_only_that_session(redis_clean: aioredis.Redis) -> None:
    store = SessionStore(redis_clean)
    a, _ = await store.create(1, UserRole.STUDENT)
    b, _ = await store.create(1, UserRole.STUDENT)
    await store.delete(a)
    assert await store.get(a) is None
    assert await store.get(b) is not None


async def test_delete_all_for_user(redis_clean: aioredis.Redis) -> None:
    store = SessionStore(redis_clean)
    a, _ = await store.create(1, UserRole.STUDENT)
    b, _ = await store.create(1, UserRole.STUDENT)
    other, _ = await store.create(2, UserRole.STUDENT)
    assert await store.delete_all_for_user(1) == 2
    assert await store.get(a) is None
    assert await store.get(b) is None
    assert await store.get(other) is not None
    assert await store.delete_all_for_user(1) == 0


async def test_session_id_is_not_stored_in_redis_in_plain(redis_clean: aioredis.Redis) -> None:
    session_id, _ = await SessionStore(redis_clean).create(1, UserRole.OWNER)
    keys = [k async for k in redis_clean.scan_iter("*")]
    assert all(session_id not in str(k) for k in keys)


def test_cookie_flags() -> None:
    from fastapi import Response

    response = Response()
    set_session_cookie(response, "abc", 100, secure=True)
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    assert "path=/" in header
    cleared = Response()
    clear_session_cookie(cleared, secure=True)
    assert "max-age=0" in cleared.headers["set-cookie"].lower()
