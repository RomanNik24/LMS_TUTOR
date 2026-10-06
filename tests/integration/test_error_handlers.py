"""Интеграционные тесты обработчиков ошибок (задача T1.01).

Единый формат ответа docs/08 §1: {"error": {"code", "message", "details"}}.
Проверяются: AppError, 422 валидация, 500 без стека наружу, 404-JSON, request_id.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.core.constants import REQUEST_ID_HEADER
from src.core.error_handlers import register_error_handlers
from src.core.exceptions import NotFoundError
from src.core.logging import RequestIdMiddleware


@pytest.fixture()
def client():
    """TestClient приложения с middleware request_id, 404→JSON и обработчиками ошибок."""
    app = FastAPI()
    app.middleware("http")(RequestIdMiddleware(app).dispatch)
    register_error_handlers(app)

    @app.get("/boom")
    async def boom() -> dict[str, bool]:
        raise RuntimeError("секретная внутренняя деталь")

    @app.get("/missing")
    async def missing() -> dict[str, bool]:
        raise NotFoundError("Урок не найден.", details={"lesson_id": 7})

    @app.post("/echo")
    async def echo(payload: dict[str, int]) -> dict[str, int]:
        return payload

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_app_error_json_format(client) -> None:
    """AppError → свой статус, code, message, details (docs/08 §1)."""
    response = client.get("/missing")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Урок не найден."
    assert body["error"]["details"] == {"lesson_id": 7}


def test_validation_error_422(client) -> None:
    """Ошибка схемы запроса → 422, code validation_error, details.fields."""
    response = client.post("/echo", json={"a": "not-an-int"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    fields = error["details"]["fields"]
    assert isinstance(fields, list) and fields
    assert {"field", "message"} <= set(fields[0])


def test_unexpected_error_500_without_stack_trace(client) -> None:
    """Неожиданное исключение → 500 internal_error; стек и текст наружу не попадают."""
    response = client.get("/boom")

    assert response.status_code == 500
    text = response.text
    assert "Traceback" not in text
    assert "RuntimeError" not in text
    assert "секретная внутренняя деталь" not in text
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["details"] == {}


def test_unknown_route_returns_json_404(client) -> None:
    """GET /nonexistent → 404 в едином JSON-формате docs/08 §1 (штатный handler)."""
    response = client.get("/nonexistent-path")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == "not_found"
    assert error["message"] == "Ресурс не найден."
    assert error["details"] == {}


def test_request_id_header_present_and_generated(client) -> None:
    """Без входящего заголовка сервер генерирует X-Request-ID."""
    response = client.get("/boom")

    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id is not None
    assert len(request_id) == 32  # uuid4().hex


def test_request_id_header_echoed_when_safe(client) -> None:
    """Корректный входящий X-Request-ID возвращается без изменений."""
    response = client.get("/missing", headers={REQUEST_ID_HEADER: "abc-123"})

    assert response.headers.get(REQUEST_ID_HEADER) == "abc-123"


def test_request_id_in_error_response_headers(client) -> None:
    """Заголовок есть и на успешном ответе — связка «ответ ↔ лог» работает."""
    response = client.post("/echo", json={"a": 1}, headers={REQUEST_ID_HEADER: "req-42"})

    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER) == "req-42"
