"""Глобальные обработчики ошибок FastAPI (задача T1.01).

Единый формат ответа по `docs/08` §1:

```json
{ "error": { "code": "...", "message": "...", "details": {} } }
```

Правила (`docs/09`, `docs/06` A5):
- прикладные ошибки отдаются классами из `src/core/exceptions.py`;
- ошибки валидации схемы — HTTP 422, код `validation_error`,
  `details.fields` — список `{field, message}`;
- неожиданные исключения — HTTP 500, код `internal_error`, нейтральное
  сообщение; stack trace и внутренние детали наружу НЕ попадают
  (полная информация — только в лог с request_id);
- тексты ошибок не должны содержать секретов и ПДн — за это отвечает
  слой сервисов, здесь дополнительно ничего не выводится из исключений.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core import texts
from src.core.constants import REQUEST_ID_HEADER
from src.core.exceptions import AppError, DetailValue
from src.core.logging import get_request_id

logger = logging.getLogger(__name__)

# Машинночитаемые коды ошибок формата docs/08 §1.
ERROR_CODE_VALIDATION = "validation_error"
ERROR_CODE_INTERNAL = "internal_error"
ERROR_CODE_NOT_FOUND = "not_found"
ERROR_CODE_METHOD_NOT_ALLOWED = "method_not_allowed"

# Соответствие HTTP-статусов машинночитаемым кодам (docs/08 §1). Для статусов
# без собственной записи в контракте — общий код по имени статуса.
HTTP_ERROR_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthenticated",
    403: "permission_denied",
    404: ERROR_CODE_NOT_FOUND,
    405: ERROR_CODE_METHOD_NOT_ALLOWED,
    409: "conflict",
    422: ERROR_CODE_VALIDATION,
    429: "rate_limited",
}

# Нейтральное сообщение для 500: внутренних деталей не раскрываем.
INTERNAL_ERROR_MESSAGE = texts.API_INTERNAL_ERROR

# Сообщение для 404 по несуществующему пути (несогласованный URL клиента).
NOT_FOUND_MESSAGE = texts.API_NOT_FOUND


def error_response(
    *,
    http_status: int,
    code: str,
    message: str,
    details: dict[str, DetailValue] | None,
    request_id: str | None = None,
) -> JSONResponse:
    """Собрать JSON-ответ об ошибке в едином формате docs/08 §1.

    Args:
        http_status: HTTP-код ответа.
        code: Машинночитаемый код ошибки.
        message: Человекочитаемое сообщение.
        details: Дополнительные данные (`{}` вместо `None`).
        request_id: Идентификатор запроса; возвращается в заголовке
            `X-Request-ID`, чтобы ошибку можно было найти в логах.

    Returns:
        Ответ `{"error": {"code", "message", "details"}}`.
    """
    payload: dict[str, object] = {
        "error": {
            "code": code,
            "message": message,
            "details": {} if details is None else details,
        }
    }
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(status_code=http_status, content=payload, headers=headers)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Обработать прикладную ошибку `AppError`: её код, статус и details.

    Args:
        request: Текущий запрос (для request_id).
        exc: Исключение, перехваченное FastAPI.

    Returns:
        JSON-ответ в формате docs/08 §1 с кодом/статусом из исключения.
    """
    return error_response(
        http_status=exc.http_status,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=get_request_id(request),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Обработать ошибку валидации запроса: HTTP 422, `details.fields`.

    Args:
        request: Текущий запрос.
        exc: `RequestValidationError` от FastAPI.

    Returns:
        JSON-ответ `{"error": {"code": "validation_error", ..., "details":
        {"fields": [{"field", "message"}]}}}`.
    """
    fields = [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return error_response(
        http_status=422,
        code=ERROR_CODE_VALIDATION,
        message=texts.API_VALIDATION_FAILED,
        details={"fields": fields},
        request_id=get_request_id(request),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обработать неожиданное исключение: 500 без стека наружу.

    Полная информация (тип и repr исключения, traceback) пишется только
    в лог вместе с request_id; клиенту отдаётся нейтральное сообщение.

    Args:
        request: Текущий запрос.
        exc: Любое непойманное исключение.

    Returns:
        JSON-ответ `{"error": {"code": "internal_error", ...}}` со статусом 500.
    """
    request_id = get_request_id(request)
    logger.exception(
        "unhandled_error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "error_repr": repr(exc),
        },
    )
    return error_response(
        http_status=500,
        code=ERROR_CODE_INTERNAL,
        message=INTERNAL_ERROR_MESSAGE,
        details={},
        request_id=request_id,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Обработать `StarletteHTTPException` в едином формате docs/08 §1.

    Starlette/FastAPI выбрасывают `HTTPException` для несуществующих путей
    (404, включая 404, сгенерированный маршрутизатором), запрещённых методов
    (405) и ответов самих эндпоинтов. Без обработчика они уходят наружу как
    `{"detail": ...}` — мимо контракта ошибок. Штатный exception-handler
    FastAPI перехватывает их все, отдельный middleware не нужен.

    Args:
        request: Текущий запрос.
        exc: Перехваченное `HTTPException`.

    Returns:
        JSON-ответ `{"error": {"code", "message", "details"}}` со статусом
        из исключения; для 404 — нейтральное сообщение контракта, `details`
        пуст (внутренний `detail` Starlette наружу не отдаём).
    """
    code = HTTP_ERROR_CODES.get(exc.status_code, ERROR_CODE_INTERNAL)
    # Для служебных сообщений Starlette ("Not Found", "Method Not Allowed")
    # отдаём нейтральные тексты из контракта, а не внутренний detail.
    if exc.status_code == 404:
        message = NOT_FOUND_MESSAGE
    elif exc.detail:
        message = str(exc.detail)
    else:
        message = INTERNAL_ERROR_MESSAGE
    details: dict[str, DetailValue] = {}
    return error_response(
        http_status=exc.status_code,
        code=code,
        message=message,
        details=details,
        request_id=get_request_id(request),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Подключить к приложению все обработчики ошибок.

    Порядок регистрации имеет смысл: собственные классы всегда важнее
    встроенных хуков Starlette/FastAPI.

    Args:
        app: Экземпляр FastAPI.
    """

    # Starlette вызывает зарегистрированный обработчик как
    # `await handler(request, exc)`; mypy strict из-за ковариантности
    # аргумента-исключения не принимает конкретные сигнатуры напрямую,
    # поэтому используются async-обёртки, сохраняющие awaited-вызов.
    Handler = Callable[[Request, Exception], Awaitable[Response]]

    async def _app_error(request: Request, exc: Exception) -> Response:
        return await app_error_handler(request, cast(AppError, exc))

    async def _http_exception(request: Request, exc: Exception) -> Response:
        return await http_exception_handler(request, cast(StarletteHTTPException, exc))

    async def _validation_error(request: Request, exc: Exception) -> Response:
        return await validation_error_handler(request, cast(RequestValidationError, exc))

    async def _unhandled_error(request: Request, exc: Exception) -> Response:
        return await unhandled_error_handler(request, exc)

    app.add_exception_handler(AppError, cast(Handler, _app_error))
    # StarletteHTTPException и RequestValidationError регистрируем и на
    # уровне приложения (add_exception_handler кладёт их в app.exception_handlers,
    # где их видит ExceptionMiddleware), и в expection_handlers уровня
    # роутера/Starlette — так «сырой» 404 маршрутизатора тоже обрабатывается
    # штатным обработчиком без дополнительного middleware.
    app.add_exception_handler(StarletteHTTPException, cast(Handler, _http_exception))
    app.add_exception_handler(RequestValidationError, cast(Handler, _validation_error))
    app.add_exception_handler(Exception, cast(Handler, _unhandled_error))
