"""REST расписания целиком (T3.07): настоящие сессии, сервисы, PostgreSQL и Redis."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.core import config as config_module
from src.core.constants import SESSION_COOKIE_NAME
from src.core.enums import UserRole
from src.core.session_store import SessionStore
from src.db.models import StudentProfile, Subject, User
from src.main import create_app

pytestmark = pytest.mark.security

BASE = "https://lms.example.com"
CSRF = {"Origin": BASE, "X-Requested-With": "XMLHttpRequest"}
START = datetime(2030, 10, 14, 14, 0, tzinfo=UTC)  # далёкое будущее: тесты не зависят от «сейчас»
PERIOD = {"from": "2030-10-01T00:00:00Z", "to": "2030-12-01T00:00:00Z"}


def iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


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
    user_id: int = 0


async def _login(app: FastAPI, db: AsyncSession, redis: aioredis.Redis, user: User) -> AuthedClient:
    session_id, _ = await SessionStore(redis).create(user.id, user.role)
    client = AuthedClient(
        transport=httpx.ASGITransport(app=app),
        base_url=BASE,
        headers=CSRF,
        cookies={SESSION_COOKIE_NAME: session_id},
    )
    client.user_id = user.id
    return client


async def _user(db: AsyncSession, role: UserRole, name: str) -> User:
    user = User(role=role, display_name=name)
    db.add(user)
    await db.commit()
    return user


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add(Subject(code="informatics", name="Информатика"))
    await db_session.commit()


@pytest.fixture
async def owner_user(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман")


@pytest.fixture
async def owner(
    app: FastAPI, db_session: AsyncSession, redis_clean: aioredis.Redis, owner_user: User
) -> AsyncIterator[AuthedClient]:
    async with await _login(app, db_session, redis_clean, owner_user) as client:
        yield client


@pytest.fixture
async def manager(
    app: FastAPI, db_session: AsyncSession, redis_clean: aioredis.Redis
) -> AsyncIterator[AuthedClient]:
    user = await _user(db_session, UserRole.MANAGER, "Мария")
    async with await _login(app, db_session, redis_clean, user) as client:
        yield client


async def _student(db: AsyncSession, teacher: User, name: str, **links: str) -> User:
    user = await _user(db, UserRole.STUDENT, name)
    db.add(StudentProfile(user_id=user.id, teacher_id=teacher.id, lesson_price=1700, **links))
    await db.commit()
    return user


@pytest.fixture
async def anya(db_session: AsyncSession, owner_user: User) -> User:
    return await _student(
        db_session,
        owner_user,
        "Аня",
        video_url="https://telemost.yandex.ru/profile-anya",
        board_url="https://miro.com/profile-anya",
    )


@pytest.fixture
async def boris(db_session: AsyncSession, owner_user: User) -> User:
    return await _student(db_session, owner_user, "Борис")


@pytest.fixture
async def anya_client(
    app: FastAPI, db_session: AsyncSession, redis_clean: aioredis.Redis, anya: User
) -> AsyncIterator[AuthedClient]:
    async with await _login(app, db_session, redis_clean, anya) as client:
        yield client


@pytest.fixture
async def boris_client(
    app: FastAPI, db_session: AsyncSession, redis_clean: aioredis.Redis, boris: User
) -> AsyncIterator[AuthedClient]:
    async with await _login(app, db_session, redis_clean, boris) as client:
        yield client


def lesson_body(
    student_ids: list[int], start: datetime = START, **extra: object
) -> dict[str, object]:
    return {
        "subject_code": "informatics",
        "student_ids": student_ids,
        "start_at": iso(start),
        "end_at": iso(start + timedelta(hours=1)),
        **extra,
    }


# ---------------------------------------------------------------- админка: уроки


async def test_staff_lesson_lifecycle_over_http(
    owner: AuthedClient, manager: AuthedClient, anya: User, boris: User
) -> None:
    created = await owner.post(
        "/api/v1/admin/lessons", json=lesson_body([anya.id, boris.id], topic="Графы")
    )
    assert created.status_code == 201
    lesson = created.json()
    lesson_id = lesson["id"]
    assert {p["student_id"] for p in lesson["participants"]} == {anya.id, boris.id}

    detail = await manager.get(f"/api/v1/admin/lessons/{lesson_id}")
    assert detail.status_code == 200
    assert detail.json()["topic"] == "Графы"

    patched = await manager.patch(
        f"/api/v1/admin/lessons/{lesson_id}",
        json={"topic": None, "teacher_note": "Повторить циклы", "student_ids": [anya.id]},
    )
    assert patched.status_code == 200
    assert patched.json()["topic"] is None
    assert patched.json()["teacher_note"] == "Повторить циклы"
    assert [p["student_id"] for p in patched.json()["participants"]] == [anya.id]

    moved = await owner.post(
        f"/api/v1/admin/lessons/{lesson_id}/reschedule",
        json={
            "start_at": iso(START + timedelta(days=1)),
            "end_at": iso(START + timedelta(days=1, hours=1)),
        },
    )
    assert moved.status_code == 200

    done = await owner.post(
        f"/api/v1/admin/lessons/{lesson_id}/complete",
        json={"marks": [{"student_id": anya.id, "attendance": "attended"}]},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    # финансовых полей в ответе нет ни у владельца, ни у менеджера
    for response in (done, await manager.get(f"/api/v1/admin/lessons/{lesson_id}")):
        assert "price" not in response.text
        assert "billable" not in response.text


async def test_overlap_is_409_and_validation_is_422(
    owner: AuthedClient, anya: User, boris: User
) -> None:
    assert (
        await owner.post("/api/v1/admin/lessons", json=lesson_body([anya.id]))
    ).status_code == 201
    clash = await owner.post(
        "/api/v1/admin/lessons", json=lesson_body([boris.id], START + timedelta(minutes=30))
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "lesson_overlap"
    bad = await owner.post(
        "/api/v1/admin/lessons", json=lesson_body([anya.id], video_url_override="http://x.ru")
    )
    assert bad.status_code == 422
    missing = await owner.get("/api/v1/admin/lessons/999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "lesson_not_found"


async def test_list_filters_period_and_pagination(
    owner: AuthedClient, anya: User, boris: User
) -> None:
    for offset, student in enumerate([anya, boris, anya]):
        start = START + timedelta(days=offset)
        assert (
            await owner.post("/api/v1/admin/lessons", json=lesson_body([student.id], start))
        ).status_code == 201
    everything = (await owner.get("/api/v1/admin/lessons", params=PERIOD)).json()
    assert everything["total"] == 3
    only_anya = (
        await owner.get("/api/v1/admin/lessons", params={**PERIOD, "student_id": anya.id})
    ).json()
    assert only_anya["total"] == 2
    page = (
        await owner.get("/api/v1/admin/lessons", params={**PERIOD, "limit": 1, "offset": 1})
    ).json()
    assert (page["total"], len(page["items"]), page["offset"]) == (3, 1, 1)
    cancelled = (
        await owner.get("/api/v1/admin/lessons", params={**PERIOD, "status": "cancelled"})
    ).json()
    assert cancelled["total"] == 0
    narrow = (
        await owner.get(
            "/api/v1/admin/lessons",
            params={"from": iso(START), "to": iso(START + timedelta(hours=2))},
        )
    ).json()
    assert narrow["total"] == 1


async def test_period_longer_than_a_year_is_rejected(owner: AuthedClient) -> None:
    for params in (
        {"from": "2030-01-01T00:00:00Z", "to": "2031-06-01T00:00:00Z"},
        {"from": "2030-02-01T00:00:00Z", "to": "2030-01-01T00:00:00Z"},
    ):
        response = await owner.get("/api/v1/admin/lessons", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_period"


# ---------------------------------------------------------------- админка: шаблоны


async def test_template_endpoints(owner: AuthedClient, manager: AuthedClient, anya: User) -> None:
    body = {
        "subject_code": "informatics",
        "student_ids": [anya.id],
        "weekday": 2,
        "start_local_time": "17:00:00",
        "timezone": "Europe/Moscow",
        "starts_on": "2030-10-01",
        "ends_on": "2030-10-31",
    }
    created = await owner.post("/api/v1/admin/schedule-templates", json=body)
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert (await manager.get("/api/v1/admin/schedule-templates")).json()[0]["id"] == template_id
    patched = await manager.patch(
        f"/api/v1/admin/schedule-templates/{template_id}", json={"duration_minutes": 90}
    )
    assert patched.status_code == 200
    assert patched.json()["duration_minutes"] == 90
    again = await owner.post(
        "/api/v1/admin/schedule-templates/generate", params={"horizon_weeks": 4}
    )
    assert again.status_code == 200
    assert again.json()["templates"] == 1
    paused = await owner.post(f"/api/v1/admin/schedule-templates/{template_id}/deactivate")
    assert paused.json()["is_active"] is False
    assert (
        await owner.patch("/api/v1/admin/schedule-templates/999999", json={"weekday": 3})
    ).status_code == 404
    assert (
        await owner.post("/api/v1/admin/schedule-templates/generate", params={"horizon_weeks": 0})
    ).status_code == 422


# ---------------------------------------------------------------- ученик


async def test_student_sees_only_own_lessons_with_resolved_links(
    owner: AuthedClient,
    anya_client: AuthedClient,
    boris_client: AuthedClient,
    anya: User,
    boris: User,
) -> None:
    group = (
        await owner.post(
            "/api/v1/admin/lessons",
            json=lesson_body(
                [anya.id, boris.id], board_url_override="https://miro.com/lesson-board"
            ),
        )
    ).json()
    solo = (
        await owner.post(
            "/api/v1/admin/lessons", json=lesson_body([boris.id], START + timedelta(days=1))
        )
    ).json()

    mine = (await anya_client.get("/api/v1/student/lessons", params=PERIOD)).json()
    assert [item["id"] for item in mine] == [group["id"]]
    card = (await anya_client.get(f"/api/v1/student/lessons/{group['id']}")).json()
    # ссылка урока важнее профиля; видео — из профиля ученика
    assert card["board_url"] == "https://miro.com/lesson-board"
    assert card["video_url"] == "https://telemost.yandex.ru/profile-anya"
    assert card["participants_count"] == 2
    # Борис без ссылок в профиле: пусто
    boris_card = (await boris_client.get(f"/api/v1/student/lessons/{group['id']}")).json()
    assert boris_card["video_url"] is None
    # чужой и несуществующий урок неразличимы: 404
    foreign = await anya_client.get(f"/api/v1/student/lessons/{solo['id']}")
    missing = await anya_client.get("/api/v1/student/lessons/999999")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == missing.json()["error"]["code"] == "lesson_not_found"


async def test_student_lesson_card_lists_only_own_linked_homework(
    owner: AuthedClient,
    anya_client: AuthedClient,
    boris_client: AuthedClient,
    anya: User,
    boris: User,
) -> None:
    """Аудит 2026-10-08, п. 6: в карточке урока — ДЗ, привязанное к уроку, только своё."""
    lesson = (
        await owner.post("/api/v1/admin/lessons", json=lesson_body([anya.id, boris.id]))
    ).json()
    other = (
        await owner.post(
            "/api/v1/admin/lessons", json=lesson_body([anya.id], START + timedelta(days=1))
        )
    ).json()
    due = iso(START + timedelta(days=3))
    base = {
        "kind": "regular",
        "subject_code": "informatics",
        "max_score": 5,
        "due_mode": "fixed",
        "due_at": due,
    }
    # привязано к уроку: Аня и Борис; привязано к другому уроку и без урока — не показывается
    for title, lesson_id, students in (
        ("Графы", lesson["id"], [anya.id, boris.id]),
        ("Для Бориса", lesson["id"], [boris.id]),
        ("Другой урок", other["id"], [anya.id]),
        ("Без урока", None, [anya.id]),
    ):
        body = {**base, "title": title, "lesson_id": lesson_id, "student_ids": students}
        assert (await owner.post("/api/v1/admin/homework", json=body)).status_code == 201

    card = (await anya_client.get(f"/api/v1/student/lessons/{lesson['id']}")).json()
    assert [(h["title"], h["status"], h["is_overdue"]) for h in card["homework"]] == [
        ("Графы", "assigned", False)
    ]
    assert card["homework"][0]["due_at"] == due
    boris_card = (await boris_client.get(f"/api/v1/student/lessons/{lesson['id']}")).json()
    assert sorted(h["title"] for h in boris_card["homework"]) == ["Графы", "Для Бориса"]
    # у другого урока свой список
    empty = (await anya_client.get(f"/api/v1/student/lessons/{other['id']}")).json()
    assert [h["title"] for h in empty["homework"]] == ["Другой урок"]


async def test_student_response_has_no_private_or_financial_data(
    owner: AuthedClient, anya_client: AuthedClient, anya: User, boris: User
) -> None:
    created = await owner.post(
        "/api/v1/admin/lessons", json=lesson_body([anya.id, boris.id], topic="Графы")
    )
    lesson_id = created.json()["id"]
    await owner.patch(
        f"/api/v1/admin/lessons/{lesson_id}", json={"teacher_note": "секретная заметка"}
    )
    for url in ("/api/v1/student/lessons", f"/api/v1/student/lessons/{lesson_id}"):
        response = await anya_client.get(url, params=PERIOD if url.endswith("lessons") else None)
        text = response.text
        for forbidden in ("секретная", "teacher_note", "price", "billable", "Борис", "1700"):
            assert forbidden not in text, (url, forbidden)


async def test_student_period_rules_and_role_separation(
    owner: AuthedClient, anya_client: AuthedClient, anya: User
) -> None:
    too_long = await anya_client.get(
        "/api/v1/student/lessons",
        params={"from": "2030-01-01T00:00:00Z", "to": "2032-01-01T00:00:00Z"},
    )
    assert too_long.status_code == 422
    # ученик не может в админку, персонал не ходит в /student
    assert (await anya_client.get("/api/v1/admin/lessons", params=PERIOD)).status_code == 403
    assert (
        await anya_client.post("/api/v1/admin/lessons", json=lesson_body([anya.id]))
    ).status_code == 403
    assert (await owner.get("/api/v1/student/lessons", params=PERIOD)).status_code == 403
