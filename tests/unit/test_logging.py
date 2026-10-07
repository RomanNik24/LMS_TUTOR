"""Юнит-тесты JSON-логирования и request_id (задача T1.01).

Проверяются: структура JSON-лога в stdout, middleware `X-Request-ID`,
фильтр PII (персональные данные в логи запрещены, разрешён только
числовой `user_id`), наличие request_id в записях лога запроса.
"""

import io
import json
import logging
from typing import TypeAlias

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.core.constants import REQUEST_ID_HEADER
from src.core.logging import NoPIIFilter, RequestIdMiddleware, setup_logging


@pytest.fixture()
def log_buffer(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Перехватывать stdout корневого логгера в буфер in-memory."""
    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    setup_logging(app_env="local")
    yield buffer
    logging.getLogger().handlers.clear()


_JsonLogLine: TypeAlias = dict[str, str | int | float | bool | None | list[str] | dict[str, object]]


def _last_json_line(buffer: io.StringIO) -> _JsonLogLine:
    """Разобрать последнюю непустую строку буфера как JSON."""
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    assert lines, "в stdout не попало ни одной записи лога"
    parsed: _JsonLogLine = json.loads(lines[-1])
    return parsed


def test_log_record_is_single_json_object(log_buffer: io.StringIO) -> None:
    """Каждая запись — один JSON-объект с базовыми полями (docs/09 §4)."""
    logging.getLogger("test.logger").info("hello_event", extra={"user_id": 42})

    record = _last_json_line(log_buffer)
    assert record["message"] == "hello_event"
    assert record["levelname"] == "INFO"
    assert record["name"] == "test.logger"
    assert record["user_id"] == 42
    # Разрешённое служебное поле present; время и уровень обязательны.
    assert "asctime" in record


def test_pii_fields_are_stripped_from_logs(log_buffer: io.StringIO) -> None:
    """PII/секреты вырезаются фильтром; user_id остаётся (docs/09 §4)."""
    logger = logging.getLogger("test.pii")
    logger.info(
        "login_attempt",
        extra={
            "user_id": 7,
            "full_name": "Иван Петров",
            "phone": "+79000000000",
            "bot_token": "123:ABC-secret",
            "init_data": "query_id=...",
            "email": "a@b.c",
        },
    )

    record = _last_json_line(log_buffer)
    assert record["user_id"] == 7
    for forbidden in ("full_name", "phone", "bot_token", "init_data", "email"):
        assert forbidden not in record, f"PII-поле {forbidden} попало в лог"
    serialized = json.dumps(record, ensure_ascii=False)
    assert "Иван" not in serialized
    assert "123:ABC-secret" not in serialized


def test_no_pii_filter_keeps_allowed_keys() -> None:
    """Фильтр не трогает обычные служебные поля и удаляет запрещённые."""
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.user_id = 5
    record.password = "hunter2"  # noqa: S105
    record.session_secret = "s3cr3t"  # noqa: S105

    assert NoPIIFilter().filter(record) is True
    assert record.user_id == 5
    assert not hasattr(record, "password")
    assert not hasattr(record, "session_secret")


def _find_record(buffer: io.StringIO, message: str) -> _JsonLogLine:
    """Вернуть распарсенную запись лога с указанным сообщением."""
    for line in buffer.getvalue().splitlines():
        if not line.strip():
            continue
        parsed: _JsonLogLine = json.loads(line)
        if parsed.get("message") == message:
            return parsed
    pytest.fail(f"запись {message!r} не найдена в логах")


def test_request_id_middleware_adds_header_and_log_field(log_buffer: io.StringIO) -> None:
    """Ответ содержит X-Request-ID, а лог запроса — поле request_id."""
    app = FastAPI()
    app.middleware("http")(RequestIdMiddleware(app).dispatch)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        logging.getLogger("app.request").info("handled_ping")
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ping", headers={REQUEST_ID_HEADER: "trace-me-1"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "trace-me-1"
    record = _find_record(log_buffer, "handled_ping")
    assert record["request_id"] == "trace-me-1"


def test_request_id_generated_when_absent(log_buffer: io.StringIO) -> None:
    """Без входящего заголовка сервер генерирует uuid4-hex request_id."""
    app = FastAPI()
    app.middleware("http")(RequestIdMiddleware(app).dispatch)

    @app.get("/pong")
    async def pong() -> dict[str, bool]:
        logging.getLogger("app.request").info("handled_pong")
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/pong")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 32
    record = _find_record(log_buffer, "handled_pong")
    assert record["request_id"] == request_id


def test_unsafe_incoming_request_id_is_replaced() -> None:
    """Подозрительный входящий X-Request-ID (пробел/длина) не принимается."""
    app = FastAPI()
    app.middleware("http")(RequestIdMiddleware(app).dispatch)

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ok", headers={REQUEST_ID_HEADER: "has space"})

    assert response.headers[REQUEST_ID_HEADER] != "has space"
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_setup_logging_is_idempotent() -> None:
    """Повторный вызов setup_logging не наслаивает хендлеры."""
    setup_logging(app_env="local")
    setup_logging(app_env="prod")
    assert len(logging.getLogger().handlers) == 1


def test_webhook_path_secret_is_redacted_in_access_log(log_buffer: io.StringIO) -> None:
    """Секретный сегмент пути вебхука не попадает в лог (uvicorn.access)."""
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:1",
        "POST",
        "/telegram/webhook/0123456789abcdef0123456789abcdef",
        "1.1",
        200,
    )
    output = log_buffer.getvalue()
    assert "0123456789abcdef" not in output
    assert "/telegram/webhook/***" in output


def test_noisy_libraries_are_quiet(log_buffer: io.StringIO) -> None:
    """asyncio и HTTP-клиенты не пишут DEBUG-шум; в prod — только WARNING."""
    assert logging.getLogger("asyncio").getEffectiveLevel() == logging.INFO
    setup_logging(app_env="prod")
    assert logging.getLogger().level == logging.INFO
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
