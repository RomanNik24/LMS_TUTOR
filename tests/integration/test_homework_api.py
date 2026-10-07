"""REST ДЗ и файлов целиком (T4.11): сессии, сервисы, PostgreSQL, Redis и S3 в памяти."""

# ruff: noqa: F401, F811 - фикстуры подключаются импортом из test_schedule_api

import io
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import deps
from src.core.constants import RATE_LIMIT_UPLOAD_COUNT
from src.db.models import User
from tests.integration.test_file_service import FakeStorage
from tests.integration.test_schedule_api import (
    AuthedClient,
    _login,
    _student,
    _subjects,
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

DUE = datetime.now(UTC) + timedelta(days=5)
FINANCE = ("price", "balance", "paid", "debt", "payment", "cost", "tariff")


def photo() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (30, 90, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


def upload(data: bytes, name: str = "work.jpg") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, data, "application/octet-stream")}


@pytest.fixture
def storage(app: FastAPI) -> FakeStorage:
    fake = FakeStorage()
    app.dependency_overrides[deps.get_object_storage] = lambda: fake
    return fake


async def create_homework(owner: AuthedClient, students: list[User], **extra: object) -> dict:
    response = await owner.post(
        "/api/v1/admin/homework",
        json={
            "kind": "regular",
            "title": "Задачи 1-5",
            "description": "Решить",
            "subject_code": "informatics",
            "max_score": 5,
            "due_mode": "fixed",
            "due_at": DUE.isoformat(),
            "student_ids": [s.id for s in students],
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def assignment_id(homework: dict, student: User) -> int:
    return next(a["id"] for a in homework["assignments"] if a["student_id"] == student.id)


def keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(key)
            found |= keys(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= keys(item)
    return found


async def test_full_cycle_over_http(
    owner: AuthedClient,
    anya_client: AuthedClient,
    anya: User,
    storage: FakeStorage,
) -> None:
    homework = await create_homework(owner, [anya])
    aid = assignment_id(homework, anya)

    material = await owner.post(
        f"/api/v1/admin/homework/{homework['id']}/materials", files=upload(photo(), "m.jpg")
    )
    assert material.status_code == 201

    listing = await anya_client.get("/api/v1/student/homework", params={"status": "active"})
    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert item["assignment_id"] == aid
    assert item["is_overdue"] is False
    assert item["extensions_left"] == 2

    card = (await anya_client.get(f"/api/v1/student/homework/{aid}")).json()
    assert card["materials"][0]["id"] == material.json()["id"]
    assert card["files"] == []

    sent = await anya_client.post(f"/api/v1/student/homework/{aid}/files", files=upload(photo()))
    assert sent.status_code == 201
    file_id = sent.json()["id"]
    assert "s3_key" not in sent.json()
    assert len(storage.objects) == 2

    link = await anya_client.get(f"/api/v1/files/{file_id}/url")
    assert link.status_code == 200
    assert link.json()["expires_in"] == 600
    mat_link = await anya_client.get(f"/api/v1/files/materials/{material.json()['id']}/url")
    assert mat_link.status_code == 200

    submitted = await anya_client.post(
        f"/api/v1/student/homework/{aid}/submit", json={"student_comment": "готово"}
    )
    assert submitted.status_code == 200
    assert submitted.json()["on_time"] is True

    queue = (await owner.get("/api/v1/admin/assignments/review-queue")).json()
    assert [row["assignment_id"] for row in queue["items"]] == [aid]
    assert queue["items"][0]["student_name"] == "Аня"

    review = await owner.post(
        f"/api/v1/admin/assignments/{aid}/review-files", files=upload(photo(), "r.jpg")
    )
    assert review.status_code == 201
    detail = (await owner.get(f"/api/v1/admin/assignments/{aid}")).json()
    assert {f["role"] for f in detail["files"]} == {"student_solution", "teacher_review"}
    assert detail["student_comment"] == "готово"

    graded = await owner.post(
        f"/api/v1/admin/assignments/{aid}/grade", json={"score": 4, "comment": "хорошо"}
    )
    assert graded.status_code == 200
    assert graded.json()["score_percent"] == 80
    out_of_range = await owner.post(f"/api/v1/admin/assignments/{aid}/grade", json={"score": 9})
    assert out_of_range.status_code == 400

    mine = (await anya_client.get("/api/v1/student/homework?status=graded")).json()
    assert mine["items"][0]["score"] == 4
    assert (await anya_client.get("/api/v1/student/homework?status=active")).json()["total"] == 0


async def test_return_extend_and_delete(
    owner: AuthedClient,
    manager: AuthedClient,
    anya_client: AuthedClient,
    anya: User,
    storage: FakeStorage,
) -> None:
    homework = await create_homework(owner, [anya])
    aid = assignment_id(homework, anya)

    first = await anya_client.post(f"/api/v1/student/homework/{aid}/files", files=upload(photo()))
    deleted = await anya_client.delete(f"/api/v1/student/homework/{aid}/files/{first.json()['id']}")
    assert deleted.status_code == 204
    assert storage.objects == {}

    extended = await manager.post(
        f"/api/v1/admin/assignments/{aid}/extend",
        json={"due_at": (DUE + timedelta(days=1)).isoformat()},
    )
    assert extended.status_code == 200
    assert extended.json()["extensions_left"] == 1
    card = (await anya_client.get(f"/api/v1/student/homework/{aid}")).json()
    assert card["extensions_left"] == 1
    assert "extensions" not in card

    done = await anya_client.post(f"/api/v1/student/homework/{aid}/self-report")
    assert done.status_code == 200
    assert done.json()["submission_type"] == "self_reported"

    returned = await manager.post(
        f"/api/v1/admin/assignments/{aid}/return",
        json={"comment": "исправь", "new_due_at": (DUE + timedelta(days=3)).isoformat()},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "needs_revision"
    staff_card = (await owner.get(f"/api/v1/admin/assignments/{aid}")).json()
    assert len(staff_card["extensions"]) == 1
    student_card = (await anya_client.get(f"/api/v1/student/homework/{aid}")).json()
    assert student_card["teacher_comment"] == "исправь"


async def test_student_cannot_touch_foreign_assignment_or_files(
    owner: AuthedClient,
    anya_client: AuthedClient,
    boris_client: AuthedClient,
    anya: User,
    boris: User,
    storage: FakeStorage,
) -> None:
    homework = await create_homework(owner, [anya, boris])
    anya_aid = assignment_id(homework, anya)
    sent = await anya_client.post(
        f"/api/v1/student/homework/{anya_aid}/files", files=upload(photo())
    )
    file_id = sent.json()["id"]
    base = f"/api/v1/student/homework/{anya_aid}"

    assert (await boris_client.get(base)).status_code == 404
    assert (await boris_client.post(f"{base}/files", files=upload(photo()))).status_code == 404
    assert (await boris_client.delete(f"{base}/files/{file_id}")).status_code == 404
    assert (await boris_client.post(f"{base}/submit")).status_code == 404
    assert (await boris_client.post(f"{base}/self-report")).status_code == 404
    assert (await boris_client.get(f"/api/v1/files/{file_id}/url")).status_code == 404
    own = (await boris_client.get("/api/v1/student/homework")).json()
    assert [row["student_id"] if "student_id" in row else 0 for row in own["items"]] == [0]
    assert own["total"] == 1


async def test_roles_matrix(
    owner: AuthedClient,
    manager: AuthedClient,
    anya_client: AuthedClient,
    anya: User,
    storage: FakeStorage,
) -> None:
    homework = await create_homework(manager, [anya])
    aid = assignment_id(homework, anya)
    student_forbidden = [
        ("get", "/api/v1/admin/homework"),
        ("post", "/api/v1/admin/homework"),
        ("get", f"/api/v1/admin/homework/{homework['id']}"),
        ("get", "/api/v1/admin/assignments"),
        ("get", "/api/v1/admin/assignments/review-queue"),
        ("get", f"/api/v1/admin/assignments/{aid}"),
        ("post", f"/api/v1/admin/assignments/{aid}/grade"),
        ("post", f"/api/v1/admin/assignments/{aid}/return"),
        ("post", f"/api/v1/admin/assignments/{aid}/extend"),
    ]
    for method, url in student_forbidden:
        response = await anya_client.request(method, url, json={})
        assert response.status_code == 403, url
    staff_forbidden = [
        ("get", "/api/v1/student/homework"),
        ("get", f"/api/v1/student/homework/{aid}"),
        ("post", f"/api/v1/student/homework/{aid}/submit"),
        ("post", f"/api/v1/student/homework/{aid}/self-report"),
    ]
    for client in (owner, manager):
        for method, url in staff_forbidden:
            assert (await client.request(method, url, json={})).status_code == 403, url
    assert (
        await anya_client.post(
            f"/api/v1/admin/assignments/{aid}/review-files", files=upload(photo())
        )
    ).status_code == 403
    assert (
        await anya_client.post(
            f"/api/v1/admin/homework/{homework['id']}/materials", files=upload(photo())
        )
    ).status_code == 403
    assert (
        await owner.post(f"/api/v1/student/homework/{aid}/files", files=upload(photo()))
    ).status_code == 403
    assert (await manager.get(f"/api/v1/admin/assignments/{aid}")).status_code == 200


async def test_anonymous_gets_401(app: FastAPI) -> None:
    import httpx
    from tests.integration.test_schedule_api import BASE, CSRF

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=BASE, headers=CSRF
    ) as client:
        for url in (
            "/api/v1/student/homework",
            "/api/v1/admin/homework",
            "/api/v1/admin/assignments",
            "/api/v1/files/1/url",
        ):
            assert (await client.get(url)).status_code == 401, url


async def test_upload_limits_and_types(
    owner: AuthedClient, anya_client: AuthedClient, anya: User, storage: FakeStorage
) -> None:
    homework = await create_homework(owner, [anya])
    url = f"/api/v1/student/homework/{assignment_id(homework, anya)}/files"

    wrong = await anya_client.post(url, files=upload(b"MZ\x90\x00not-an-image", "virus.pdf"))
    assert wrong.status_code == 415
    assert wrong.json()["error"]["code"] == "unsupported_file_type"
    big = await anya_client.post(url, files=upload(b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 1)))
    assert big.status_code == 413
    assert big.json()["error"]["code"] == "file_too_large"
    empty = await anya_client.post(url, files=upload(b""))
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "empty_file"
    missing = await anya_client.post(url)
    assert missing.status_code == 422
    assert storage.objects == {}


async def test_upload_rate_limit(
    owner: AuthedClient, anya_client: AuthedClient, anya: User, storage: FakeStorage
) -> None:
    homework = await create_homework(owner, [anya])
    url = f"/api/v1/student/homework/{assignment_id(homework, anya)}/files"
    for _ in range(RATE_LIMIT_UPLOAD_COUNT):
        response = await anya_client.post(url, files=upload(b"junk"))
        assert response.status_code == 415
    limited = await anya_client.post(url, files=upload(photo()))
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"


async def test_filters_pagination_and_privacy(
    owner: AuthedClient,
    anya_client: AuthedClient,
    anya: User,
    boris: User,
    storage: FakeStorage,
) -> None:
    first = await create_homework(owner, [anya, boris], title="Раз")
    await create_homework(owner, [anya], title="Два")

    page = (await owner.get("/api/v1/admin/assignments", params={"limit": 2})).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    only_boris = (
        await owner.get("/api/v1/admin/assignments", params={"student_id": boris.id})
    ).json()
    assert [row["title"] for row in only_boris["items"]] == ["Раз"]
    assert (await owner.get("/api/v1/admin/assignments?status=graded")).json()["total"] == 0
    assert (await owner.get("/api/v1/admin/assignments?overdue=true")).json()["total"] == 0
    assert (await owner.get("/api/v1/admin/assignments?limit=0")).status_code == 422
    assert (await anya_client.get("/api/v1/student/homework?status=bogus")).status_code == 422

    homeworks = (await owner.get("/api/v1/admin/homework")).json()
    assert homeworks["total"] == 2
    added = await owner.post(
        f"/api/v1/admin/homework/{first['id']}/assignees", json={"student_ids": [anya.id]}
    )
    assert added.status_code == 200

    aid = assignment_id(first, anya)
    student_payload = (await anya_client.get(f"/api/v1/student/homework/{aid}")).json()
    student_list = (await anya_client.get("/api/v1/student/homework")).json()
    for payload in (student_payload, student_list):
        names = keys(payload)
        assert not [n for n in names if any(t in n.lower() for t in FINANCE)]
        assert not [n for n in names if "teacher_note" in n]
        assert "student_name" not in names and "extensions" not in names


async def test_overdue_flag(
    owner: AuthedClient,
    anya_client: AuthedClient,
    anya: User,
    storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    from sqlalchemy import update
    from src.db.models import HomeworkAssignment

    homework = await create_homework(owner, [anya])
    aid = assignment_id(homework, anya)
    await db_session.execute(
        update(HomeworkAssignment)
        .where(HomeworkAssignment.id == aid)
        .values(due_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()
    card = (await anya_client.get(f"/api/v1/student/homework/{aid}")).json()
    assert card["is_overdue"] is True
    flagged = (await owner.get("/api/v1/admin/assignments?overdue=true")).json()
    assert flagged["total"] == 1 and flagged["items"][0]["is_overdue"] is True
