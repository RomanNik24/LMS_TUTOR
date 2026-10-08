"""HTTP-слой ``/admin/*`` (T2.04) без БД: сервисы подменены, проверяются роли, коды, форматы.

Что здесь проверяется: роутеры, зависимости ролей (настоящий ``RoleChecker``), валидация запросов,
CSRF, единый формат ошибок, сериализация «разного DTO по роли» (цена только владельцу), ссылка
приглашения. Логика сервисов покрыта интеграционными тестами (``tests/integration``).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from src.api import deps
from src.core import config as config_module
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import BusinessRuleError, NotFoundError
from src.main import create_app
from src.schemas.staff import StaffCreate, StaffItem, StaffListPage, StaffUpdate
from src.schemas.students import (
    StudentCardManager,
    StudentCardOwner,
    StudentCreate,
    StudentListPage,
    StudentUpdate,
)
from src.services.auth import IssuedToken
from src.services.students import StudentStatus

BASE = "https://lms.example.com"
CSRF = {"Origin": BASE, "X-Requested-With": "XMLHttpRequest"}
EXPIRES = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def _card(actor: CurrentUser, student_id: int = 5) -> StudentCardManager | StudentCardOwner:
    """Карточка по роли — как в настоящем ``StudentService._card``."""
    common: dict[str, Any] = {
        "user_id": student_id,
        "display_name": "Аня",
        "timezone": "Europe/Moscow",
        "is_active": True,
        "bot_blocked": False,
        "telegram_linked": False,
        "teacher_id": 1,
        "school_class": 9,
        "video_url": None,
        "board_url": None,
        "teacher_notes": "заметка",
        "subjects": ["math"],
    }
    if actor.role == UserRole.OWNER:
        return StudentCardOwner(**common, lesson_price=1500)
    return StudentCardManager(**common)


def _staff_item(role: UserRole = UserRole.MANAGER) -> StaffItem:
    return StaffItem(
        user_id=7,
        display_name="Мария",
        role=role,
        timezone="Europe/Moscow",
        is_active=True,
        bot_blocked=False,
        telegram_linked=False,
        invite_pending=True,
    )


class FakeStudents:
    """Подмена ``StudentService``: возвращает заготовки или бросает заданную ошибку."""

    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _go(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if self.error is not None:
            raise self.error

    async def list_students(self, actor: CurrentUser, **kwargs: Any) -> StudentListPage:
        self._go("list", kwargs)
        return StudentListPage(items=[], total=0, limit=kwargs["limit"], offset=kwargs["offset"])

    async def create_student(self, actor: CurrentUser, data: StudentCreate) -> Any:
        self._go("create", data)
        return _card(actor)

    async def get_student_card_for_staff(self, actor: CurrentUser, student_id: int) -> Any:
        self._go("get", student_id)
        return _card(actor, student_id)

    async def update_student(self, actor: CurrentUser, student_id: int, data: StudentUpdate) -> Any:
        self._go("update", student_id, data)
        return _card(actor, student_id)

    async def archive_student(self, actor: CurrentUser, student_id: int) -> Any:
        self._go("archive", student_id)
        return _card(actor, student_id)

    async def restore_student(self, actor: CurrentUser, student_id: int) -> Any:
        self._go("restore", student_id)
        return _card(actor, student_id)

    async def invite_student(self, actor: CurrentUser, student_id: int) -> IssuedToken:
        self._go("invite", student_id)
        return IssuedToken(id=11, token="TOKEN123", expires_at=EXPIRES)  # noqa: S106 - тестовое значение

    async def unlink_telegram(self, actor: CurrentUser, student_id: int) -> None:
        self._go("unlink", student_id)


class FakeStaff:
    """Подмена ``StaffService``."""

    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _go(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if self.error is not None:
            raise self.error

    async def list_staff(self, actor: CurrentUser, **kwargs: Any) -> StaffListPage:
        self._go("list", kwargs)
        return StaffListPage(items=[_staff_item()], total=1, limit=kwargs["limit"], offset=0)

    async def create_staff(self, actor: CurrentUser, data: StaffCreate) -> StaffItem:
        self._go("create", data)
        return _staff_item(data.role)

    async def update_staff(self, actor: CurrentUser, staff_id: int, data: StaffUpdate) -> StaffItem:
        self._go("update", staff_id, data)
        return _staff_item()

    async def invite_staff(self, actor: CurrentUser, staff_id: int) -> IssuedToken:
        self._go("invite", staff_id)
        return IssuedToken(id=12, token="STAFFTOKEN", expires_at=EXPIRES)  # noqa: S106 - тестовое значение

    async def archive_staff(self, actor: CurrentUser, staff_id: int) -> StaffItem:
        self._go("archive", staff_id)
        return _staff_item()


class FakeAuth:
    """Подмена ``AuthService`` для ``DELETE /admin/invitations/{id}``."""

    def __init__(self) -> None:
        self.error: Exception | None = None
        self.revoked: list[int] = []

    async def revoke_invitation(self, actor: CurrentUser, invitation_id: int) -> None:
        if self.error is not None:
            raise self.error
        self.revoked.append(invitation_id)


class World:
    """Текущий пользователь и подмены сервисов для одного теста."""

    def __init__(self) -> None:
        self.role = UserRole.OWNER
        self.students = FakeStudents()
        self.staff = FakeStaff()
        self.auth = FakeAuth()

    def actor(self) -> CurrentUser:
        return CurrentUser(id=1, role=self.role, timezone="Europe/Moscow")


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def app(world: World, app_settings_env: None, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    monkeypatch.setenv("BOT_USERNAME", "testbot")
    config_module.get_settings.cache_clear()
    application = create_app("local")
    application.dependency_overrides[deps.current_user] = world.actor
    application.dependency_overrides[deps.get_student_service] = lambda: world.students
    application.dependency_overrides[deps.get_staff_service] = lambda: world.staff
    application.dependency_overrides[deps.get_auth_service] = lambda: world.auth
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=CSRF) as c:
        yield c


# ------------------------------------------------------------------ роли и приватность


async def test_manager_card_has_no_price_but_owner_card_has(
    client: httpx.AsyncClient, world: World
) -> None:
    world.role = UserRole.MANAGER
    manager_json = (await client.get("/api/v1/admin/students/5")).json()
    assert "lesson_price" not in manager_json
    assert manager_json["teacher_notes"] == "заметка"
    world.role = UserRole.OWNER
    owner_json = (await client.get("/api/v1/admin/students/5")).json()
    assert owner_json["lesson_price"] == 1500


async def test_price_is_hidden_from_manager_in_every_student_response(
    client: httpx.AsyncClient, world: World
) -> None:
    world.role = UserRole.MANAGER
    responses = [
        await client.post("/api/v1/admin/students", json={"display_name": "Аня"}),
        await client.patch("/api/v1/admin/students/5", json={"school_class": 10}),
        await client.post("/api/v1/admin/students/5/archive"),
        await client.post("/api/v1/admin/students/5/restore"),
    ]
    assert [r.status_code for r in responses] == [201, 200, 200, 200]
    assert all("lesson_price" not in r.json() for r in responses)


async def test_student_gets_403_everywhere_in_admin(
    client: httpx.AsyncClient, world: World
) -> None:
    world.role = UserRole.STUDENT
    calls = [
        client.get("/api/v1/admin/students"),
        client.post("/api/v1/admin/students", json={"display_name": "X"}),
        client.get("/api/v1/admin/students/5"),
        client.patch("/api/v1/admin/students/5", json={"school_class": 9}),
        client.post("/api/v1/admin/students/5/archive"),
        client.post("/api/v1/admin/students/5/restore"),
        client.post("/api/v1/admin/students/5/invitations"),
        client.post("/api/v1/admin/students/5/unlink-telegram"),
        client.delete("/api/v1/admin/invitations/3"),
        client.get("/api/v1/admin/staff"),
        client.post("/api/v1/admin/staff", json={"display_name": "X"}),
        client.patch("/api/v1/admin/staff/7", json={"display_name": "Y"}),
        client.post("/api/v1/admin/staff/7/invitations"),
        client.post("/api/v1/admin/staff/7/archive"),
    ]
    for call in calls:
        response = await call
        assert response.status_code == 403, response.request.url
        assert response.json()["error"]["code"] == "permission_denied"
    assert world.students.calls == []
    assert world.staff.calls == []


async def test_manager_gets_403_on_every_owner_only_endpoint(
    client: httpx.AsyncClient, world: World
) -> None:
    world.role = UserRole.MANAGER
    calls = [
        client.get("/api/v1/admin/staff"),
        client.post("/api/v1/admin/staff", json={"display_name": "X"}),
        client.patch("/api/v1/admin/staff/7", json={"role": "owner"}),
        client.post("/api/v1/admin/staff/7/invitations"),
        client.post("/api/v1/admin/staff/7/archive"),
    ]
    for call in calls:
        response = await call
        assert response.status_code == 403, response.request.url
    assert world.staff.calls == []


async def test_owner_can_use_staff_endpoints(client: httpx.AsyncClient, world: World) -> None:
    listing = await client.get("/api/v1/admin/staff?include_archived=true&limit=10")
    created = await client.post(
        "/api/v1/admin/staff", json={"display_name": "Совладелец", "role": "owner"}
    )
    updated = await client.patch("/api/v1/admin/staff/7", json={"role": "manager"})
    archived = await client.post("/api/v1/admin/staff/7/archive")
    assert [r.status_code for r in (listing, created, updated, archived)] == [200, 201, 200, 200]
    assert listing.json()["total"] == 1
    assert created.json()["role"] == "owner"
    assert world.staff.calls[0] == ("list", ({"include_archived": True, "limit": 10, "offset": 0},))


async def test_unauthenticated_request_is_401(app: FastAPI) -> None:
    app.dependency_overrides.pop(deps.current_user)
    # Без cookie сессии БД и Redis не используются: достаточно заглушек зависимостей.
    app.dependency_overrides[deps.get_session] = lambda: None
    app.dependency_overrides[deps.get_redis] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=CSRF) as anonymous:
        response = await anonymous.get("/api/v1/admin/students")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


# ------------------------------------------------------------------ запросы и CSRF


async def test_state_changing_requests_need_csrf_headers(app: FastAPI, world: World) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as bare:
        no_headers = await bare.post("/api/v1/admin/students", json={"display_name": "Аня"})
        no_origin = await bare.post(
            "/api/v1/admin/students",
            json={"display_name": "Аня"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
    assert no_headers.status_code == 403
    assert no_origin.status_code == 403
    assert world.students.calls == []


async def test_validation_errors_use_the_common_format(client: httpx.AsyncClient) -> None:
    cases = [
        client.post(
            "/api/v1/admin/students",
            json={"display_name": "Аня", "video_url": "http://meet.example.com"},
        ),
        client.post("/api/v1/admin/students", json={"display_name": "Аня", "lesson_price": -5}),
        client.post("/api/v1/admin/students", json={"display_name": "Аня", "role": "owner"}),
        client.patch("/api/v1/admin/students/5", json={}),
        client.get("/api/v1/admin/students?limit=0"),
        client.get("/api/v1/admin/students?limit=201"),
        client.get("/api/v1/admin/students?offset=-1"),
        client.get("/api/v1/admin/students?status=deleted"),
        client.get("/api/v1/admin/students/0"),
        client.post("/api/v1/admin/staff", json={"display_name": "X", "role": "student"}),
        client.patch("/api/v1/admin/staff/7", json={"role": None}),
        client.delete("/api/v1/admin/invitations/0"),
    ]
    for call in cases:
        response = await call
        assert response.status_code == 422, response.request.url
        body = response.json()["error"]
        assert body["code"] == "validation_error"
        assert body["details"]["fields"]


async def test_list_passes_filters_and_returns_page(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.get("/api/v1/admin/students?status=archived&q=Ан&limit=20&offset=40")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 40}
    assert world.students.calls == [
        ("list", ({"status": StudentStatus.ARCHIVED, "q": "Ан", "limit": 20, "offset": 40},))
    ]


async def test_update_passes_only_sent_fields(client: httpx.AsyncClient, world: World) -> None:
    await client.patch("/api/v1/admin/students/5", json={"video_url": None, "lesson_price": 900})
    name, args = world.students.calls[0]
    assert name == "update"
    assert args[0] == 5
    assert args[1].model_fields_set == {"video_url", "lesson_price"}


# ------------------------------------------------------------------ приглашения и ошибки


async def test_student_invitation_returns_ready_link_once(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/admin/students/5/invitations")
    assert response.status_code == 201
    assert response.json() == {
        "id": 11,
        "url": "https://t.me/testbot?start=inv_TOKEN123",
        "expires_at": "2026-10-14T12:00:00Z",
    }


async def test_staff_invitation_link(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/admin/staff/7/invitations")
    assert response.status_code == 201
    assert response.json()["url"] == "https://t.me/testbot?start=inv_STAFFTOKEN"
    assert response.json()["id"] == 12


async def test_revoke_invitation_and_unlink_return_204(
    client: httpx.AsyncClient, world: World
) -> None:
    revoke = await client.delete("/api/v1/admin/invitations/11")
    unlink = await client.post("/api/v1/admin/students/5/unlink-telegram")
    assert revoke.status_code == 204
    assert unlink.status_code == 204
    assert revoke.content == b""
    assert world.auth.revoked == [11]
    assert world.students.calls == [("unlink", (5,))]


async def test_service_errors_are_mapped_to_documented_codes(
    client: httpx.AsyncClient, world: World
) -> None:
    world.students.error = NotFoundError("Ученик не найден.")
    missing = await client.get("/api/v1/admin/students/999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    world.students.error = BusinessRuleError(
        "Ученик уже в архиве.", code="student_already_archived"
    )
    twice = await client.post("/api/v1/admin/students/5/archive")
    assert twice.status_code == 400
    assert twice.json()["error"]["code"] == "student_already_archived"

    world.staff.error = BusinessRuleError("последний", code="last_owner")
    last = await client.patch("/api/v1/admin/staff/1", json={"role": "manager"})
    assert last.status_code == 400
    assert last.json()["error"]["code"] == "last_owner"

    world.auth.error = NotFoundError("нет", code="invite_not_found")
    gone = await client.delete("/api/v1/admin/invitations/11")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "invite_not_found"


async def test_operation_ids_are_stable(app: FastAPI) -> None:
    ids = {
        operation["operationId"]
        for path, methods in app.openapi()["paths"].items()
        if "/admin/" in path
        for operation in methods.values()
    }
    assert ids == {
        "list_students",
        "create_student",
        "get_student",
        "update_student",
        "archive_student",
        "restore_student",
        "create_student_invitation",
        "unlink_student_telegram",
        "revoke_invitation",
        "list_staff",
        "create_staff",
        "update_staff",
        "create_staff_invitation",
        "archive_staff",
        # расписание (T3.07)
        "list_lessons",
        "create_lesson",
        "get_lesson",
        "update_lesson",
        "reschedule_lesson",
        "cancel_lesson",
        "complete_lesson",
        "list_schedule_templates",
        "create_schedule_template",
        "generate_lessons",
        "update_schedule_template",
        "deactivate_schedule_template",
        # домашние задания (T4.11)
        "list_homework",
        "create_homework",
        "get_homework",
        "add_homework_assignees",
        "upload_homework_material",
        "list_assignments",
        "list_review_queue",
        "get_assignment",
        "grade_assignment",
        "return_assignment",
        "extend_assignment",
        "upload_review_file",
        # пробные экзамены (T6.03)
        "list_mock_exams",
        "create_mock_exam",
        "convert_mock_exam_score",
        "update_mock_exam",
        "delete_mock_exam",
    }
