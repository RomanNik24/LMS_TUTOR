"""Схема ответа эндпоинта проверки живости приложения."""

from pydantic import BaseModel

from src.core.constants import HEALTH_STATUS_OK


class HealthResponse(BaseModel):
    """Ответ `GET /health`.

    Attributes:
        status: Статус приложения.
    """

    status: str = HEALTH_STATUS_OK
