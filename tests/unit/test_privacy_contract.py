"""Контракт приватности ответов API по ролям (T2.01, docs/08 §8, docs/09 §3).

Тест обходит OpenAPI-схему приложения и падает, если в ответах эндпоинтов ``/student/*`` и
``/admin/*`` есть запрещённое поле. Эндпоинты подхватываются автоматически: достаточно, чтобы
роутер был подключён к приложению и защищён ``require_role``.

Правила:
- у каждого эндпоинта ``/student/*`` и ``/admin/*`` есть ``require_role`` (иначе нельзя понять,
  кому он доступен): ``/student/*`` — только ``student``,
  ``/admin/*`` — ``owner`` и/или ``manager``;
- ответ ``/student/*`` не содержит ни денег (``lesson_price``, ``price_snapshot``, ``is_billable``,
  сумм), ни ``teacher_notes`` / ``teacher_note``, ни схем, предназначенных менеджеру или владельцу;
- ответ эндпоинта, доступного менеджеру, не содержит денег. Исключение — схема владельца
  (метка ``x-audience: owner``) как член верхнеуровневого ``anyOf``/``oneOf`` рядом со схемой
  менеджера: так выглядит «разный DTO по роли» на одном пути (docs/08 §9). Какой вариант отдать,
  решает сервис, и это проверяют тесты сервисов;
- эндпоинты, доступные только владельцу, не проверяются: финансы ему видны.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, routing
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from pydantic import BaseModel
from src.api.deps import RoleChecker, require_role
from src.core.enums import UserRole
from src.main import create_app
from src.schemas.roles import AUDIENCE_KEY, STUDENT_HIDDEN_FIELDS, audience_config, is_finance_field
from src.schemas.students import StudentCardManager, StudentCardOwner, StudentSelfProfile

pytestmark = pytest.mark.security

API_PREFIX = "/api/v1"
STUDENT_PREFIX = f"{API_PREFIX}/student/"
ADMIN_PREFIX = f"{API_PREFIX}/admin/"
REF_PREFIX = "#/components/schemas/"

JsonSchema = dict[str, Any]


# ------------------------------------------------------------------ обход OpenAPI


def _property_names(node: object) -> Iterator[str]:
    """Имена свойств внутри схемы, включая вложенные inline-схемы ($ref не раскрываем)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                yield from value
            yield from _property_names(value)
    elif isinstance(node, list):
        for item in node:
            yield from _property_names(item)


def _refs(node: object) -> Iterator[str]:
    """Имена схем, на которые ссылается узел (``$ref``)."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(REF_PREFIX):
            yield ref.removeprefix(REF_PREFIX)
        for value in node.values():
            yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def _reachable(components: dict[str, JsonSchema], node: object) -> dict[str, JsonSchema]:
    """Все именованные схемы, достижимые из узла по ссылкам."""
    found: dict[str, JsonSchema] = {}
    stack = list(_refs(node))
    while stack:
        name = stack.pop()
        if name in found:
            continue
        found[name] = components[name]
        stack.extend(_refs(components[name]))
    return found


def _audience(schema: JsonSchema) -> str | None:
    value = schema.get(AUDIENCE_KEY)
    return value if isinstance(value, str) else None


def _members(root: JsonSchema) -> list[JsonSchema]:
    """Верхнеуровневые варианты ответа (``anyOf``/``oneOf``) или сам ответ."""
    variants = root.get("anyOf") or root.get("oneOf")
    return list(variants) if isinstance(variants, list) else [root]


def _forbidden_in(node: object, *, student: bool) -> list[str]:
    """Запрещённые имена свойств внутри узла (без раскрытия ссылок)."""
    bad = []
    for name in _property_names(node):
        if is_finance_field(name) or (student and name in STUDENT_HIDDEN_FIELDS):
            bad.append(name)
    return bad


def _check_response(
    components: dict[str, JsonSchema], root: JsonSchema, *, student: bool
) -> list[str]:
    """Нарушения в ответе эндпоинта, доступного ученику или менеджеру."""
    problems: list[str] = []
    members = _members(root)
    owner_refs = [m for m in members if (ref := m.get("$ref")) and _is_owner_ref(components, ref)]
    others = [m for m in members if m not in owner_refs]
    if owner_refs and (student or not others):
        problems.append(
            "схема владельца в ответе, доступном "
            + ("ученику" if student else "менеджеру без отдельного варианта для менеджера")
        )
    for member in others:
        problems += [f"запрещённое поле «{n}»" for n in _forbidden_in(member, student=student)]
        for name, schema in _reachable(components, member).items():
            problems += [
                f"запрещённое поле «{n}» в схеме {name}"
                for n in _forbidden_in(schema, student=student)
            ]
            audience = _audience(schema)
            if audience == UserRole.OWNER.value or (student and audience == UserRole.MANAGER.value):
                problems.append(f"схема {name} предназначена для роли {audience}")
    return problems


def _is_owner_ref(components: dict[str, JsonSchema], ref: object) -> bool:
    if not isinstance(ref, str) or not ref.startswith(REF_PREFIX):
        return False
    return _audience(components[ref.removeprefix(REF_PREFIX)]) == UserRole.OWNER.value


# ------------------------------------------------------------------ роли эндпоинтов


def _walk(dependant: Dependant) -> Iterator[Dependant]:
    for child in dependant.dependencies:
        yield child
        yield from _walk(child)


@dataclass(frozen=True)
class ApiEndpoint:
    """Эндпоинт приложения: путь, методы и дерево зависимостей."""

    path: str
    methods: frozenset[str]
    dependant: Dependant


def iter_api_endpoints(app: FastAPI) -> Iterator[ApiEndpoint]:
    """Все эндпоинты приложения, включая подключённые через ``include_router``.

    В свежих версиях FastAPI ``app.routes`` содержит «вложенные роутеры», а не плоский список,
    поэтому используется ``fastapi.routing.iter_route_contexts``; в старых — плоский список.
    """
    iterate = getattr(routing, "iter_route_contexts", None)
    if iterate is None:
        for route in app.routes:
            if isinstance(route, APIRoute):
                yield ApiEndpoint(route.path_format, frozenset(route.methods), route.dependant)
        return
    for context in iterate(app.routes):
        dependant = getattr(context, "dependant", None)
        path = context.path_format
        if isinstance(dependant, Dependant) and path:
            yield ApiEndpoint(path, frozenset(context.methods or ()), dependant)


def _route_roles(endpoint: ApiEndpoint) -> frozenset[UserRole] | None:
    """Роли из ``require_role`` эндпоинта; ``None`` — проверки роли нет."""
    roles: set[UserRole] = set()
    found = False
    for dependency in _walk(endpoint.dependant):
        if isinstance(dependency.call, RoleChecker):
            found = True
            roles |= dependency.call.roles
    return frozenset(roles) if found else None


def find_privacy_violations(app: FastAPI) -> list[str]:
    """Все нарушения контракта приватности в приложении (пустой список — всё чисто)."""
    openapi = app.openapi()
    components: dict[str, JsonSchema] = openapi.get("components", {}).get("schemas", {})
    violations: list[str] = []
    for route in iter_api_endpoints(app):
        path = route.path
        in_student = path.startswith(STUDENT_PREFIX)
        in_admin = path.startswith(ADMIN_PREFIX)
        if not (in_student or in_admin):
            continue
        roles = _route_roles(route)
        for method in sorted(route.methods):
            where = f"{method} {path}"
            if roles is None:
                violations.append(f"{where}: нет require_role")
                continue
            if in_student and roles != {UserRole.STUDENT}:
                violations.append(f"{where}: /student/* только для student, сейчас {sorted(roles)}")
                continue
            if in_admin and (not roles or not roles <= {UserRole.OWNER, UserRole.MANAGER}):
                violations.append(f"{where}: /admin/* только для owner и manager")
                continue
            if in_admin and UserRole.MANAGER not in roles:
                continue  # только владелец: финансы ему видны
            operation = openapi["paths"][path][method.lower()]
            for code, response in operation.get("responses", {}).items():
                if not str(code).startswith("2"):
                    continue
                root = response.get("content", {}).get("application/json", {}).get("schema")
                if not isinstance(root, dict):
                    continue
                violations += [
                    f"{where} [{code}]: {problem}"
                    for problem in _check_response(components, root, student=in_student)
                ]
    return violations


# ------------------------------------------------------------------ тесты на реальном приложении


def test_walker_sees_endpoints_included_via_include_router() -> None:
    """Защита от пустого обхода: известные эндпоинты реального приложения должны находиться."""
    paths = {endpoint.path for endpoint in iter_api_endpoints(create_app())}
    assert {f"{API_PREFIX}/me", f"{API_PREFIX}/auth/telegram", "/health"} <= paths


def test_real_app_has_no_privacy_violations() -> None:
    """Все текущие и будущие эндпоинты /student/* и /admin/* соблюдают контракт."""
    assert find_privacy_violations(create_app()) == []


def test_role_schemas_follow_the_rules() -> None:
    """Схемы по ролям: ученик и менеджер без денег, ученик без заметок, у владельца есть цена."""
    for schema in (StudentSelfProfile, StudentCardManager):
        names = set(schema.model_json_schema()["properties"])
        assert not [n for n in names if is_finance_field(n)], schema.__name__
    assert not set(StudentSelfProfile.model_json_schema()["properties"]) & STUDENT_HIDDEN_FIELDS
    assert "teacher_notes" in StudentCardManager.model_json_schema()["properties"]
    assert "lesson_price" in StudentCardOwner.model_json_schema()["properties"]
    assert StudentCardOwner.model_json_schema()[AUDIENCE_KEY] == "owner"
    assert StudentCardManager.model_json_schema()[AUDIENCE_KEY] == "manager"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("lesson_price", True),
        ("price_snapshot", True),
        ("is_billable", True),
        ("earned_month", True),
        ("earned", True),
        ("expected_month", True),
        ("total_amount", True),
        ("price_text", False),  # публичный текст витрины каталога
        ("summary", False),
        ("display_name", False),
    ],
)
def test_finance_field_detection(name: str, expected: bool) -> None:
    assert is_finance_field(name) is expected


# ------------------------------------------------------------------ тесты самого обходчика


class _Public(BaseModel):
    title: str


class _WithPrice(BaseModel):
    title: str
    lesson_price: int


class _WithNotes(BaseModel):
    title: str
    teacher_notes: str | None = None


class _Nested(BaseModel):
    inner: _WithPrice


class _ManagerDto(BaseModel):
    model_config = audience_config(UserRole.MANAGER)

    title: str
    teacher_notes: str | None = None


class _OwnerDto(_ManagerDto):
    model_config = audience_config(UserRole.OWNER)

    lesson_price: int


def _app_with(prefix: str, roles: tuple[UserRole, ...], response_model: Any) -> FastAPI:
    """Приложение с одним эндпоинтом ``GET <prefix>x`` и заданным ответом."""
    app = FastAPI()
    router = APIRouter(prefix=prefix)

    @router.get("/x", response_model=response_model, dependencies=[Depends(require_role(*roles))])
    async def endpoint() -> Any:
        return None

    app.include_router(router)
    return app


STUDENT = f"{API_PREFIX}/student"
ADMIN = f"{API_PREFIX}/admin"


def test_detects_price_in_student_response() -> None:
    """Красный сценарий: lesson_price в схеме ответа ученика."""
    violations = find_privacy_violations(_app_with(STUDENT, (UserRole.STUDENT,), _WithPrice))
    assert any("lesson_price" in v for v in violations), violations


def test_detects_teacher_notes_in_student_response_but_allows_them_for_manager() -> None:
    student = find_privacy_violations(_app_with(STUDENT, (UserRole.STUDENT,), _WithNotes))
    manager = find_privacy_violations(_app_with(ADMIN, (UserRole.MANAGER,), _WithNotes))
    assert any("teacher_notes" in v for v in student), student
    assert manager == []


def test_detects_price_nested_in_list_and_in_other_schema() -> None:
    nested = find_privacy_violations(_app_with(STUDENT, (UserRole.STUDENT,), _Nested))
    in_list = find_privacy_violations(_app_with(ADMIN, (UserRole.MANAGER,), list[_WithPrice]))
    assert any("lesson_price" in v for v in nested), nested
    assert any("lesson_price" in v for v in in_list), in_list


def test_detects_price_in_manager_response_and_allows_it_for_owner_only() -> None:
    manager = find_privacy_violations(_app_with(ADMIN, (UserRole.MANAGER,), _WithPrice))
    both = find_privacy_violations(_app_with(ADMIN, (UserRole.OWNER, UserRole.MANAGER), _WithPrice))
    owner_only = find_privacy_violations(_app_with(ADMIN, (UserRole.OWNER,), _WithPrice))
    assert any("lesson_price" in v for v in manager), manager
    assert any("lesson_price" in v for v in both), both
    assert owner_only == []


def test_owner_dto_is_allowed_only_next_to_manager_dto() -> None:
    """«Разный DTO по роли»: union из схемы менеджера и владельца допустим для менеджера."""
    union = _app_with(ADMIN, (UserRole.OWNER, UserRole.MANAGER), _OwnerDto | _ManagerDto)
    only_owner_dto = _app_with(ADMIN, (UserRole.OWNER, UserRole.MANAGER), _OwnerDto)
    student_union = _app_with(STUDENT, (UserRole.STUDENT,), _OwnerDto | _ManagerDto)
    assert find_privacy_violations(union) == []
    assert any("владельца" in v for v in find_privacy_violations(only_owner_dto))
    assert find_privacy_violations(student_union) != []


def test_clean_endpoints_pass() -> None:
    assert find_privacy_violations(_app_with(STUDENT, (UserRole.STUDENT,), _Public)) == []
    assert find_privacy_violations(_app_with(ADMIN, (UserRole.MANAGER,), _Public)) == []


def test_endpoint_without_role_check_is_a_violation() -> None:
    app = FastAPI()

    @app.get(f"{ADMIN}/open", response_model=_Public)
    async def open_endpoint() -> Any:
        return None

    assert any("нет require_role" in v for v in find_privacy_violations(app))


def test_student_prefix_requires_student_role_only() -> None:
    app = _app_with(STUDENT, (UserRole.STUDENT, UserRole.MANAGER), _Public)
    assert any("только для student" in v for v in find_privacy_violations(app))
    assert any(
        "owner и manager" in v
        for v in find_privacy_violations(_app_with(ADMIN, (UserRole.STUDENT,), _Public))
    )
