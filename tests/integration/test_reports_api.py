"""REST отчётов (T6.04): ``GET /student/reports`` и ``GET /admin/students/{id}/report``."""

# ruff: noqa: F401, F811 - фикстуры подключаются импортом из test_schedule_api

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import AssignmentStatus, DueMode, HomeworkKind
from src.db.models import Homework, HomeworkAssignment, Subject, User
from tests.integration.test_homework_api import FINANCE, keys
from tests.integration.test_schedule_api import (
    AuthedClient,
    anya,
    anya_client,
    app,
    boris,
    boris_client,
    manager,
    owner,
    owner_user,
    redis_clean,
)

pytestmark = pytest.mark.security

PERIOD = {"from": "2026-10-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"}


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add(Subject(code="informatics", name="Информатика"))
    await db_session.commit()


async def grade(db: AsyncSession, owner_user: User, student: User, score: int) -> None:
    subject = (await db.execute(Subject.__table__.select())).first()
    assert subject is not None
    homework = Homework(
        created_by=owner_user.id,
        subject_id=subject.id,
        kind=HomeworkKind.REGULAR,
        title="ДЗ",
        max_score=10,
        due_mode=DueMode.FIXED,
    )
    db.add(homework)
    await db.flush()
    moment = datetime(2026, 10, 7, 12, tzinfo=UTC)
    db.add(
        HomeworkAssignment(
            homework_id=homework.id,
            student_id=student.id,
            status=AssignmentStatus.GRADED,
            original_due_at=moment,
            due_at=moment,
            submitted_at=moment,
            graded_at=moment,
            score=score,
        )
    )
    await db.commit()


async def test_student_gets_only_own_report(
    anya_client: AuthedClient,
    boris_client: AuthedClient,
    db_session: AsyncSession,
    owner_user: User,
    anya: User,
    boris: User,
) -> None:
    await grade(db_session, owner_user, anya, 9)
    await grade(db_session, owner_user, boris, 4)

    mine = await anya_client.get("/api/v1/student/reports", params=PERIOD)
    assert mine.status_code == 200, mine.text
    body = mine.json()
    assert body["student_id"] == anya.id
    assert [(p["week_start"], p["average_percent"]) for p in body["homework_weekly"]] == [
        ("2026-10-05", 90)
    ]
    assert body["on_time"] == {"on_time_count": 1, "total_count": 1, "percent": 100}
    boris_body = (await boris_client.get("/api/v1/student/reports", params=PERIOD)).json()
    assert boris_body["homework_weekly"][0]["average_percent"] == 40


async def test_staff_reads_any_student_report_without_finance(
    manager: AuthedClient,
    owner: AuthedClient,
    db_session: AsyncSession,
    owner_user: User,
    anya: User,
) -> None:
    await grade(db_session, owner_user, anya, 7)
    for staff in (manager, owner):
        response = await staff.get(f"/api/v1/admin/students/{anya.id}/report", params=PERIOD)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["homework_last_percent"] == 70
        assert not {k for k in keys(payload) if any(f in k.lower() for f in FINANCE)}
        assert not {"lesson_price", "price_snapshot", "teacher_notes"} & keys(payload)


async def test_report_access_and_errors(
    anya_client: AuthedClient,
    manager: AuthedClient,
    app: FastAPI,
    anya: User,
    boris: User,
) -> None:
    # ученик не может смотреть админский отчёт (даже свой), персонал — студенческий
    assert (
        await anya_client.get(f"/api/v1/admin/students/{anya.id}/report", params=PERIOD)
    ).status_code == 403
    assert (await manager.get("/api/v1/student/reports", params=PERIOD)).status_code == 403
    unknown = await manager.get("/api/v1/admin/students/999999/report", params=PERIOD)
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "student_not_found")
    staff_id = (await manager.get("/api/v1/me")).json()["id"]
    not_student = await manager.get(f"/api/v1/admin/students/{staff_id}/report", params=PERIOD)
    assert not_student.status_code == 404
    for path in ("/api/v1/student/reports", f"/api/v1/admin/students/{anya.id}/report"):
        client = manager if "admin" in path else anya_client
        reverse = {"from": PERIOD["to"], "to": PERIOD["from"]}
        too_long = {"from": "2025-01-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"}
        for params in (reverse, too_long):
            response = await client.get(path, params=params)
            assert (response.status_code, response.json()["error"]["code"]) == (
                422,
                "invalid_period",
            )
        assert (await client.get(path)).status_code == 422  # период обязателен
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=str(anya_client.base_url)
    ) as anonymous:
        assert (await anonymous.get("/api/v1/student/reports", params=PERIOD)).status_code == 401
