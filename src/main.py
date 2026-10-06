"""Точка входа backend-приложения MY_LMS.

Приложение создаётся без lifespan: подключение к БД, Redis и Telegram-бот
появляются в следующих задачах этапа 0. Ядро T1.01 — JSON-логи с
request_id и глобальные обработчики ошибок в едином формате docs/08 §1
(AppError, HTTPException/404, валидация 422, неожиданные 500 без стека).
"""

from fastapi import FastAPI

from src.core.constants import HEALTH_STATUS_OK
from src.core.error_handlers import register_error_handlers
from src.core.logging import RequestIdMiddleware, setup_logging
from src.schemas.health import HealthResponse

# Логи — JSON в stdout, request_id из контекста запроса (docs/09 §4).
setup_logging()

app = FastAPI(
    title="MY_LMS API",
    version="0.1.0",
)

# request_id доступен всем обработчикам ошибок через ContextVar (docs/09 §4).
app.middleware("http")(RequestIdMiddleware(app).dispatch)

register_error_handlers(app)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Проверка живости приложения",
    operation_id="health_check",
)
async def health_check() -> HealthResponse:
    """Вернуть статус приложения.

    Returns:
        Ответ со статусом `ok`.
    """
    return HealthResponse(status=HEALTH_STATUS_OK)
