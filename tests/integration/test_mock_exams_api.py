"""REST пробных экзаменов (T6.03, docs/08 §5.6): настоящие сессии, сервисы, PostgreSQL и Redis."""

# ruff: noqa: F401, F811 - фикстуры подключаются импортом из test_schedule_api

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from src.db.models import ExamType, User
from tests.integration.test_homework_api import FINANCE, assignment_id, keys
from tests.integration.test_schedule_api import (
    AuthedClient,
    anya,
    anya_client,
    app,
    boris,
    manager,
    owner,
    owner_user,
    redis_clean,
)

pytestmark = pytest.mark.security

URL = "/api/v1/admin/mock-exams"
DUE = datetime.now(UTC) + timedelta(days=5)


def body(student: User, exam: ExamType, primary: int, **extra: object) -> dict[str, object]:
    return {
        "student_id": student.id,
        "exam_type_id": exam.id,
        "exam_date": "2026-05-20",
        "primary_score": primary,
        "max_primary": exam.max_primary,
        **extra,
    }


async def create_mock_homework(owner: AuthedClient, student: User, exam: ExamType) -> dict:
    response = await owner.post(
        "/api/v1/admin/homework",
        json={
            "kind": "mock_exam",
            "title": "Пробник",
            "exam_type_id": exam.id,
            "due_mode": "fixed",
            "due_at": DUE.isoformat(),
            "student_ids": [student.id],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def submit(client: AuthedClient, assignment: int) -> None:
    response = await client.post(
        f"/api/v1/student/homework/{assignment}/self-report", json={"student_comment": "готово"}
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------- ручной ввод


async def test_manual_result_is_converted_and_listed(
    manager: AuthedClient, anya: User, seeded_reference: dict[str, ExamType]
) -> None:
    exam = seeded_reference["ege_informatics"]
    created = await manager.post(URL, json=body(anya, exam, 20, comment="  Вариант 3  "))
    assert created.status_code == 201, created.text
    item = created.json()
    assert (item["converted_value"], item["scale_year"], item["scale_applicable"]) == (
        78,
        2026,
        True,
    )
    assert (item["assignment_id"], item["comment"], item["student_name"]) == (
        None,
        "Вариант 3",
        "Аня",
    )
    assert item["exam_type_code"] == "ege_informatics"
    listed = (await manager.get(URL, params={"student_id": anya.id})).json()
    assert [r["id"] for r in listed["items"]] == [item["id"]]
    assert listed["total"] == 1


async def test_nonstandard_maximum_has_no_scale(
    manager: AuthedClient, anya: User, seeded_reference: dict[str, ExamType]
) -> None:
    """«Пробник по информатике на 27 баллов» (docs/04 §10.4): шкала неприменима."""
    exam = seeded_reference["ege_informatics"]
    response = await manager.post(URL, json={**body(anya, exam, 20), "max_primary": 27})
    item = response.json()
    assert (item["converted_value"], item["scale_year"], item["scale_applicable"]) == (
        None,
        None,
        False,
    )


async def test_oge_math_geometry_rule_and_warning(
    manager: AuthedClient, anya: User, seeded_reference: dict[str, ExamType]
) -> None:
    exam = seeded_reference["oge_math"]
    low = (await manager.post(URL, json=body(anya, exam, 22, geometry_score=1))).json()
    assert (low["converted_value"], low["warning"]) == (2, None)
    ok = (await manager.post(URL, json=body(anya, exam, 22, geometry_score=2))).json()
    assert (ok["converted_value"], ok["warning"]) == (5, None)
    unknown = (await manager.post(URL, json=body(anya, exam, 22))).json()
    assert (unknown["converted_value"], unknown["warning"]) == (5, "geometry_missing")


async def test_validation_errors(
    manager: AuthedClient, anya: User, seeded_reference: dict[str, ExamType]
) -> None:
    ege = seeded_reference["ege_informatics"]
    oge = seeded_reference["oge_math"]

    over = await manager.post(URL, json=body(anya, ege, 30))
    assert (over.status_code, over.json()["error"]["code"]) == (400, "score_out_of_range")
    not_oge = await manager.post(URL, json=body(anya, ege, 20, geometry_score=1))
    assert not_oge.json()["error"]["code"] == "geometry_not_applicable"
    too_big = await manager.post(URL, json=body(anya, oge, 5, geometry_score=6))
    assert too_big.json()["error"]["code"] == "geometry_too_big"
    unknown_student = await manager.post(URL, json={**body(anya, ege, 20), "student_id": 999_999})
    assert (unknown_student.status_code, unknown_student.json()["error"]["code"]) == (
        404,
        "student_not_found",
    )
    unknown_exam = await manager.post(URL, json={**body(anya, ege, 20), "exam_type_id": 999_999})
    assert unknown_exam.json()["error"]["code"] == "exam_type_not_found"
    negative = await manager.post(URL, json=body(anya, ege, -1))
    assert negative.status_code == 422
    # сотрудник не может быть «учеником» пробника
    staff_id = (await manager.get("/api/v1/me")).json()["id"]
    as_staff = await manager.post(URL, json={**body(anya, ege, 20), "student_id": staff_id})
    assert as_staff.json()["error"]["code"] == "student_not_found"


async def test_convert_preview_does_not_save(
    manager: AuthedClient, seeded_reference: dict[str, ExamType]
) -> None:
    exam = seeded_reference["oge_informatics"]
    request = {
        "exam_type_id": exam.id,
        "exam_date": "2026-05-20",
        "primary_score": 17,
        "max_primary": 21,
    }
    response = await manager.post(f"{URL}/convert", json=request)
    assert response.status_code == 200
    assert response.json() == {
        "converted_value": 5,
        "scale_year": 2026,
        "scale_applicable": True,
        "warning": None,
    }
    assert (await manager.get(URL)).json()["total"] == 0
    bad = await manager.post(f"{URL}/convert", json={**request, "primary_score": 22})
    assert bad.json()["error"]["code"] == "score_out_of_range"


async def test_patch_recalculates_and_delete_removes_manual_result(
    manager: AuthedClient, anya: User, seeded_reference: dict[str, ExamType]
) -> None:
    exam = seeded_reference["oge_informatics"]
    item = (await manager.post(URL, json=body(anya, exam, 10, comment="x"))).json()
    assert item["converted_value"] == 3

    changed = await manager.patch(
        f"{URL}/{item['id']}", json={"primary_score": 11, "comment": None}
    )
    assert changed.status_code == 200, changed.text
    assert (changed.json()["converted_value"], changed.json()["comment"]) == (4, None)
    # смена максимума делает шкалу неприменимой, возврат — снова применимой
    odd = await manager.patch(f"{URL}/{item['id']}", json={"max_primary": 20})
    assert odd.json()["scale_applicable"] is False
    back = await manager.patch(f"{URL}/{item['id']}", json={"max_primary": 21})
    assert back.json()["converted_value"] == 4
    assert (await manager.patch(f"{URL}/{item['id']}", json={})).status_code == 422
    above = await manager.patch(f"{URL}/{item['id']}", json={"primary_score": 22})
    assert above.json()["error"]["code"] == "score_out_of_range"
    # неизвестное поле (например, смена ученика) отклоняется
    assert (await manager.patch(f"{URL}/{item['id']}", json={"student_id": 1})).status_code == 422

    assert (await manager.delete(f"{URL}/{item['id']}")).status_code == 204
    gone = await manager.delete(f"{URL}/{item['id']}")
    assert (gone.status_code, gone.json()["error"]["code"]) == (404, "mock_exam_not_found")
    assert (await manager.get(URL)).json()["total"] == 0


async def test_list_filters_and_pagination(
    manager: AuthedClient, anya: User, boris: User, seeded_reference: dict[str, ExamType]
) -> None:
    ege, oge = seeded_reference["ege_informatics"], seeded_reference["oge_informatics"]
    rows = ((anya, ege, "2026-03-01"), (anya, oge, "2026-04-01"), (boris, ege, "2026-05-01"))
    for student, exam, day in rows:
        await manager.post(URL, json={**body(student, exam, 5), "exam_date": day})
    everything = (await manager.get(URL)).json()
    assert [r["exam_date"] for r in everything["items"]] == [
        "2026-05-01",
        "2026-04-01",
        "2026-03-01",
    ]
    only_anya = (await manager.get(URL, params={"student_id": anya.id})).json()
    assert only_anya["total"] == 2
    only_ege = (await manager.get(URL, params={"exam_type_id": ege.id})).json()
    assert only_ege["total"] == 2
    page = (await manager.get(URL, params={"limit": 1, "offset": 1})).json()
    assert (page["total"], [r["exam_date"] for r in page["items"]]) == (3, ["2026-04-01"])
    invalid = await manager.get(URL, params={"limit": 0})
    assert invalid.json()["error"]["code"] == "invalid_list_params"


# ---------------------------------------------------------------- из оценки ДЗ


async def test_grading_mock_homework_creates_and_updates_result(
    owner: AuthedClient,
    manager: AuthedClient,
    anya: User,
    anya_client: AuthedClient,
    seeded_reference: dict[str, ExamType],
) -> None:
    exam = seeded_reference["oge_math"]
    homework = await create_mock_homework(owner, anya, exam)
    assignment = assignment_id(homework, anya)
    detail = (await owner.get(f"/api/v1/admin/assignments/{assignment}")).json()
    assert detail["exam_type_id"] == exam.id
    await submit(anya_client, assignment)

    graded = await manager.post(
        f"/api/v1/admin/assignments/{assignment}/grade", json={"score": 22, "geometry_score": 1}
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["conversion"]["converted_value"] == 2  # геометрия < 2

    results = (await manager.get(URL, params={"student_id": anya.id})).json()
    assert results["total"] == 1
    first = results["items"][0]
    assert (first["assignment_id"], first["primary_score"], first["max_primary"]) == (
        assignment,
        22,
        31,
    )
    assert first["converted_value"] == 2

    regraded = await manager.post(
        f"/api/v1/admin/assignments/{assignment}/grade", json={"score": 24, "geometry_score": 3}
    )
    assert regraded.json()["conversion"]["converted_value"] == 5
    again = (await manager.get(URL, params={"student_id": anya.id})).json()
    assert again["total"] == 1  # обновлён, а не продублирован
    assert (again["items"][0]["id"], again["items"][0]["primary_score"]) == (first["id"], 24)

    # связанные с ДЗ результаты правятся через оценку: PATCH и DELETE запрещены
    patch = await manager.patch(f"{URL}/{first['id']}", json={"primary_score": 1})
    delete = await manager.delete(f"{URL}/{first['id']}")
    for response in (patch, delete):
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "mock_exam_linked_to_homework"


async def test_invalid_geometry_when_grading_does_not_change_the_assignment(
    owner: AuthedClient,
    manager: AuthedClient,
    anya: User,
    anya_client: AuthedClient,
    seeded_reference: dict[str, ExamType],
) -> None:
    exam = seeded_reference["ege_informatics"]
    homework = await create_mock_homework(owner, anya, exam)
    assignment = assignment_id(homework, anya)
    await submit(anya_client, assignment)
    bad = await manager.post(
        f"/api/v1/admin/assignments/{assignment}/grade", json={"score": 20, "geometry_score": 1}
    )
    assert bad.json()["error"]["code"] == "geometry_not_applicable"
    detail = (await manager.get(f"/api/v1/admin/assignments/{assignment}")).json()
    assert detail["status"] == "submitted"  # откат: оценка не сохранилась
    assert (await manager.get(URL)).json()["total"] == 0


async def test_regular_homework_grade_has_no_conversion(
    owner: AuthedClient,
    manager: AuthedClient,
    anya: User,
    anya_client: AuthedClient,
    seeded_reference: dict[str, ExamType],
) -> None:
    created = await owner.post(
        "/api/v1/admin/homework",
        json={
            "kind": "regular",
            "title": "Обычное",
            "subject_code": "informatics",
            "max_score": 5,
            "due_mode": "fixed",
            "due_at": DUE.isoformat(),
            "student_ids": [anya.id],
        },
    )
    assert created.status_code == 201, created.text
    assignment = assignment_id(created.json(), anya)
    await submit(anya_client, assignment)
    graded = await manager.post(f"/api/v1/admin/assignments/{assignment}/grade", json={"score": 4})
    assert graded.json()["conversion"] is None
    assert (await manager.get(URL)).json()["total"] == 0


# ---------------------------------------------------------------- права и приватность


async def test_student_and_anonymous_have_no_access(
    anya_client: AuthedClient, app: FastAPI, seeded_reference: dict[str, ExamType], anya: User
) -> None:
    exam = seeded_reference["ege_informatics"]
    for method, path, payload in (
        ("GET", URL, None),
        ("POST", URL, body(anya, exam, 5)),
        ("POST", f"{URL}/convert", {}),
        ("PATCH", f"{URL}/1", {"comment": "x"}),
        ("DELETE", f"{URL}/1", None),
    ):
        response = await anya_client.request(method, path, json=payload)
        assert response.status_code == 403, (method, path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=str(anya_client.base_url)
    ) as anonymous:
        assert (await anonymous.get(URL)).status_code == 401


async def test_responses_have_no_financial_fields(
    manager: AuthedClient, anya: User, seeded_reference: dict[str, ExamType]
) -> None:
    exam = seeded_reference["ege_informatics"]
    created = (await manager.post(URL, json=body(anya, exam, 20))).json()
    listed = (await manager.get(URL)).json()
    for payload in (created, listed):
        assert not {k for k in keys(payload) if any(f in k.lower() for f in FINANCE)}
        assert not {"lesson_price", "price_snapshot", "teacher_notes"} & keys(payload)
