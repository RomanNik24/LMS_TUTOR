"""/admin/* целиком: настоящие сессии, сервисы, PostgreSQL и Redis (T2.04, docs/08 §8)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.core import config as config_module
from src.core.constants import SESSION_COOKIE_NAME
from src.core.enums import AuthTokenPurpose, UserRole
from src.core.security import hash_token
from src.core.session_store import SessionStore
from src.db.models import AuditLog, AuthToken, Subject, User
from src.main import create_app

pytestmark = pytest.mark.security

BASE = "https://lms.example.com"
CSRF = {"Origin": BASE, "X-Requested-With": "XMLHttpRequest"}


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
    monkeypatch.setenv("BOT_USERNAME", "testbot")
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.setenv("SENTRY_DSN", "")
    config_module.get_settings.cache_clear()
    application = create_app("local")

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[deps.get_session] = _session
    application.dependency_overrides[deps.get_redis] = lambda: redis_clean
    yield application
    config_module.get_settings.cache_clear()


class AuthedClient(httpx.AsyncClient):
    """HTTP-клиент с сессией пользователя; ``user_id`` — его ``users.id``."""

    user_id: int = 0


async def _login(
    app: FastAPI, db: AsyncSession, redis: aioredis.Redis, role: UserRole, name: str
) -> AuthedClient:
    """Клиент с настоящей сессией пользователя заданной роли."""
    user = User(role=role, display_name=name, telegram_id=None)
    db.add(user)
    await db.commit()
    session_id, _ = await SessionStore(redis).create(user.id, role)
    transport = httpx.ASGITransport(app=app)
    client = AuthedClient(
        transport=transport,
        base_url=BASE,
        headers=CSRF,
        cookies={SESSION_COOKIE_NAME: session_id},
    )
    client.user_id = user.id
    return client


@pytest.fixture
async def owner(
    app: FastAPI, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> AsyncIterator[AuthedClient]:
    async with await _login(app, db_session, redis_clean, UserRole.OWNER, "Роман") as client:
        yield client


@pytest.fixture
async def manager(
    app: FastAPI, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> AsyncIterator[AuthedClient]:
    async with await _login(app, db_session, redis_clean, UserRole.MANAGER, "Мария") as client:
        yield client


@pytest.fixture
async def student(
    app: FastAPI, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> AsyncIterator[AuthedClient]:
    async with await _login(app, db_session, redis_clean, UserRole.STUDENT, "Аня") as client:
        yield client


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            Subject(code="informatics", name="Информатика"),
            Subject(code="math", name="Математика"),
        ]
    )
    await db_session.commit()


async def _actions(db: AsyncSession, action: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
    return list((await db.execute(stmt)).scalars().all())


# ---------------------------------------------------------------- ученики по ролям


async def test_student_and_anonymous_are_rejected_on_admin(
    student: AuthedClient, app: FastAPI
) -> None:
    for method, url in (
        ("GET", "/api/v1/admin/students"),
        ("POST", "/api/v1/admin/students"),
        ("GET", "/api/v1/admin/staff"),
        ("DELETE", "/api/v1/admin/invitations/1"),
    ):
        response = await student.request(
            method, url, json={"display_name": "X"} if method == "POST" else None
        )
        assert response.status_code == 403, url
        assert response.json()["error"]["code"] == "permission_denied"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=CSRF) as anonymous:
        assert (await anonymous.get("/api/v1/admin/students")).status_code == 401


async def test_owner_creates_student_with_price_and_manager_never_sees_it(
    owner: AuthedClient, manager: AuthedClient, db_session: AsyncSession
) -> None:
    created = await owner.post(
        "/api/v1/admin/students",
        json={
            "display_name": "Аня",
            "school_class": 9,
            "subject_codes": ["math"],
            "lesson_price": 1500,
            "teacher_notes": "заметка",
        },
    )
    assert created.status_code == 201
    student_id = created.json()["user_id"]
    assert created.json()["lesson_price"] == 1500

    as_manager = await manager.get(f"/api/v1/admin/students/{student_id}")
    assert as_manager.status_code == 200
    assert "lesson_price" not in as_manager.json()
    assert as_manager.json()["teacher_notes"] == "заметка"
    as_owner = await owner.get(f"/api/v1/admin/students/{student_id}")
    assert as_owner.json()["lesson_price"] == 1500

    listing = await manager.get("/api/v1/admin/students")
    assert listing.json()["total"] == 1
    assert "lesson_price" not in listing.json()["items"][0]

    # менеджер не может ни задать цену при создании, ни изменить её
    denied_create = await manager.post(
        "/api/v1/admin/students", json={"display_name": "Боря", "lesson_price": 1}
    )
    denied_patch = await manager.patch(
        f"/api/v1/admin/students/{student_id}", json={"lesson_price": 1}
    )
    assert denied_create.status_code == 403
    assert denied_patch.status_code == 403
    assert (await owner.get(f"/api/v1/admin/students/{student_id}")).json()["lesson_price"] == 1500

    changed = await owner.patch(
        f"/api/v1/admin/students/{student_id}", json={"lesson_price": 2000, "school_class": 11}
    )
    assert changed.status_code == 200
    assert changed.json()["lesson_price"] == 2000
    entries = await _actions(db_session, "student.price_changed")
    assert [e.data for e in entries] == [{"old": 1500, "new": 2000}]


async def test_missing_student_is_404_and_bad_input_is_422(owner: AuthedClient) -> None:
    missing = await owner.get("/api/v1/admin/students/999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    bad_link = await owner.post(
        "/api/v1/admin/students",
        json={"display_name": "Аня", "video_url": "http://meet.example.com"},
    )
    assert bad_link.status_code == 422
    unknown_subject = await owner.post(
        "/api/v1/admin/students", json={"display_name": "Аня", "subject_codes": ["physics"]}
    )
    assert unknown_subject.status_code == 422
    assert unknown_subject.json()["error"]["code"] == "unknown_subject"


async def test_archive_restore_and_session_removal(
    owner: AuthedClient, app: FastAPI, redis_clean: aioredis.Redis
) -> None:
    created = await owner.post("/api/v1/admin/students", json={"display_name": "Аня"})
    student_id = created.json()["user_id"]
    session_id, _ = await SessionStore(redis_clean).create(student_id, UserRole.STUDENT)

    archived = await owner.post(f"/api/v1/admin/students/{student_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    assert await SessionStore(redis_clean).get(session_id) is None
    again = await owner.post(f"/api/v1/admin/students/{student_id}/archive")
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "student_already_archived"

    archived_list = await owner.get("/api/v1/admin/students?status=archived")
    assert [i["user_id"] for i in archived_list.json()["items"]] == [student_id]
    restored = await owner.post(f"/api/v1/admin/students/{student_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["is_active"] is True


# ---------------------------------------------------------------- приглашения


async def test_invitation_link_is_shown_once_and_can_be_revoked(
    owner: AuthedClient, manager: AuthedClient, db_session: AsyncSession
) -> None:
    created = await owner.post("/api/v1/admin/students", json={"display_name": "Аня"})
    student_id = created.json()["user_id"]

    issued = await manager.post(f"/api/v1/admin/students/{student_id}/invitations")
    assert issued.status_code == 201
    body = issued.json()
    assert body["url"].startswith("https://t.me/testbot?start=inv_")
    token = body["url"].split("start=inv_")[1]
    record = (
        await db_session.execute(select(AuthToken).where(AuthToken.id == body["id"]))
    ).scalar_one()
    assert record.token_hash == hash_token(token)  # в БД только хэш
    assert record.purpose == AuthTokenPurpose.INVITE
    assert record.user_id == student_id

    reissued = await manager.post(f"/api/v1/admin/students/{student_id}/invitations")
    assert reissued.json()["id"] != body["id"]
    await db_session.refresh(record)
    assert record.revoked_at is not None  # прежнее приглашение отозвано

    revoked = await manager.delete(f"/api/v1/admin/invitations/{reissued.json()['id']}")
    assert revoked.status_code == 204
    again = await manager.delete(f"/api/v1/admin/invitations/{reissued.json()['id']}")
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "invite_not_found"
    assert (await manager.delete("/api/v1/admin/invitations/999999")).status_code == 404


async def test_unlink_telegram_via_api(owner: AuthedClient, db_session: AsyncSession) -> None:
    created = await owner.post("/api/v1/admin/students", json={"display_name": "Аня"})
    student_id = created.json()["user_id"]
    user = await db_session.get(User, student_id)
    assert user is not None
    user.telegram_id = 940_001
    await db_session.commit()

    response = await owner.post(f"/api/v1/admin/students/{student_id}/unlink-telegram")

    assert response.status_code == 204
    await db_session.refresh(user)
    assert user.telegram_id is None
    again = await owner.post(f"/api/v1/admin/students/{student_id}/unlink-telegram")
    assert again.status_code == 400


# ---------------------------------------------------------------- сотрудники (только owner)


async def test_manager_gets_403_on_staff_endpoints_and_cannot_revoke_staff_invitation(
    owner: AuthedClient, manager: AuthedClient
) -> None:
    staff = await owner.post("/api/v1/admin/staff", json={"display_name": "Новый"})
    staff_id = staff.json()["user_id"]
    invitation = await owner.post(f"/api/v1/admin/staff/{staff_id}/invitations")
    assert invitation.status_code == 201

    for method, url, payload in (
        ("GET", "/api/v1/admin/staff", None),
        ("POST", "/api/v1/admin/staff", {"display_name": "X"}),
        ("PATCH", f"/api/v1/admin/staff/{staff_id}", {"role": "owner"}),
        ("POST", f"/api/v1/admin/staff/{staff_id}/invitations", None),
        ("POST", f"/api/v1/admin/staff/{staff_id}/archive", None),
    ):
        response = await manager.request(method, url, json=payload)
        assert response.status_code == 403, url
    # приглашение сотрудника менеджер отозвать не может, владелец — может
    revoke_by_manager = await manager.delete(f"/api/v1/admin/invitations/{invitation.json()['id']}")
    assert revoke_by_manager.status_code == 403
    revoke_by_owner = await owner.delete(f"/api/v1/admin/invitations/{invitation.json()['id']}")
    assert revoke_by_owner.status_code == 204


async def test_owner_manages_staff_and_last_owner_is_protected(
    owner: AuthedClient, manager: AuthedClient, db_session: AsyncSession
) -> None:
    owner_id = owner.user_id
    manager_id = manager.user_id

    listing = await owner.get("/api/v1/admin/staff")
    assert listing.status_code == 200
    assert {i["display_name"] for i in listing.json()["items"]} == {"Роман", "Мария"}

    last = await owner.patch(f"/api/v1/admin/staff/{owner_id}", json={"role": "manager"})
    assert last.status_code == 400
    assert last.json()["error"]["code"] == "last_owner"
    archive_last = await owner.post(f"/api/v1/admin/staff/{owner_id}/archive")
    assert archive_last.status_code == 400
    assert archive_last.json()["error"]["code"] == "last_owner"

    promoted = await owner.patch(f"/api/v1/admin/staff/{manager_id}", json={"role": "owner"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "owner"
    assert len(await _actions(db_session, "staff.role_changed")) == 1
    # менеджер стал владельцем: теперь понизить исходного владельца уже можно
    demoted = await owner.patch(f"/api/v1/admin/staff/{owner_id}", json={"role": "manager"})
    assert demoted.status_code == 200
    student_as_staff = await owner.patch("/api/v1/admin/staff/999999", json={"display_name": "X"})
    assert student_as_staff.status_code == 404
