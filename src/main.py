"""Точка входа backend-приложения MY_LMS.

Приложение создаётся без lifespan: подключение к БД, Redis и Telegram-бот
появляются в следующих задачах этапа 0.
"""

from fastapi import FastAPI

from src.core.constants import HEALTH_STATUS_OK
from src.schemas.health import HealthResponse

app = FastAPI(
    title="MY_LMS API",
    version="0.1.0",
)


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
