"""Схема ответа эндпоинта проверки живости приложения."""

from pydantic import BaseModel

from src.core.constants import HEALTH_COMPONENT_OK, HEALTH_STATUS_OK


class HealthResponse(BaseModel):
    """Ответ `GET /health` (docs/08 §3: проверка БД и Redis).

    Attributes:
        status: `ok` — всё работает; `degraded` — недоступна БД или Redis (HTTP 503).
        database: Состояние PostgreSQL: `ok` или `error`.
        redis: Состояние Redis: `ok` или `error`.
    """

    status: str = HEALTH_STATUS_OK
    database: str = HEALTH_COMPONENT_OK
    redis: str = HEALTH_COMPONENT_OK
