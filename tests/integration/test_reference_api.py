"""Справочники ``/reference/*`` (docs/08 §3): предметы и типы экзаменов берутся из БД.

Аудит 2026-10-08, п. 4: эндпоинтов не было, и фронтенд держал список предметов в своём коде.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.core import config as config_module
from src.core.constants import SESSION_COOKIE_NAME
from src.core.enums import ExamKind, ExamResultKind, UserRole
from src.core.session_store import SessionStore
from src.db.models import ExamType, Subject, User
from src.main import create_app

BASE = "https://lms.example.com"


@pytest.fixture
def app(
    db_session: AsyncSession, redis_client: aioredis.Redis, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.setenv("SENTRY_DSN", "")
    config_module.get_settings.cache_clear()
    application = create_app("local")

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[deps.get_session] = _session
    application.dependency_overrides[deps.get_redis] = lambda: redis_client
    yield application
    config_module.get_settings.cache_clear()


@pytest.fixture
async def reference(db_session: AsyncSession) -> None:
    informatics = Subject(code="informatics", name="Информатика")
    math = Subject(code="math", name="Математика")
    retired = Subject(code="physics", name="Физика", is_active=False)
    db_session.add_all([informatics, math, retired])
    await db_session.flush()
    db_session.add_all(
        [
            ExamType(
                code="ege_informatics",
                subject_id=informatics.id,
                kind=ExamKind.EGE,
                result_kind=ExamResultKind.TEST_100,
                max_primary=29,
                name="ЕГЭ — Информатика",
            ),
            ExamType(
                code="oge_math",
                subject_id=math.id,
                kind=ExamKind.OGE,
                result_kind=ExamResultKind.GRADE_2_5,
                max_primary=31,
                name="ОГЭ — Математика",
                config={"min_geometry": 2},
            ),
            ExamType(
                code="oge_physics",
                subject_id=retired.id,
                kind=ExamKind.OGE,
                result_kind=ExamResultKind.GRADE_2_5,
                max_primary=45,
                name="ОГЭ — Физика",
                is_active=False,
            ),
        ]
    )
    await db_session.commit()


async def _client(
    app: FastAPI, redis: aioredis.Redis, db: AsyncSession, role: UserRole
) -> httpx.AsyncClient:
    user = User(role=role, display_name="Тест")
    db.add(user)
    await db.commit()
    session_id, _ = await SessionStore(redis).create(user.id, user.role)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=BASE,
        cookies={SESSION_COOKIE_NAME: session_id},
    )


@pytest.mark.usefixtures("reference")
@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.MANAGER, UserRole.OWNER])
async def test_any_signed_in_user_reads_active_subjects_and_exam_types(
    app: FastAPI, redis_client: aioredis.Redis, db_session: AsyncSession, role: UserRole
) -> None:
    await redis_client.flushdb()
    async with await _client(app, redis_client, db_session, role) as client:
        subjects = await client.get("/api/v1/reference/subjects")
        exams = await client.get("/api/v1/reference/exam-types")
    assert subjects.status_code == 200
    assert subjects.json() == [
        {"code": "informatics", "name": "Информатика"},
        {"code": "math", "name": "Математика"},
    ]
    assert exams.status_code == 200
    body = exams.json()
    assert [item["code"] for item in body] == ["ege_informatics", "oge_math"]
    assert body[1] == {
        "id": body[1]["id"],
        "code": "oge_math",
        "subject_code": "math",
        "kind": "oge",
        "result_kind": "grade_2_5",
        "max_primary": 31,
        "name": "ОГЭ — Математика",
        "uses_geometry": True,
    }


@pytest.mark.usefixtures("reference")
async def test_reference_requires_sign_in(app: FastAPI) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        for path in ("/api/v1/reference/subjects", "/api/v1/reference/exam-types"):
            response = await client.get(path)
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "unauthenticated"
