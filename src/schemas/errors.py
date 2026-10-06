"""Схемы ошибок для OpenAPI (docs/08 §1, docs/06 A6).

Нужны, чтобы в OpenAPI (и в типах фронтенда) были модели для всех кодов ответа.
"""

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Тело ошибки.

    Attributes:
        code: Машинночитаемый код (``unauthenticated``, ``rate_limited``, …).
        message: Сообщение для пользователя.
        details: Дополнительные данные (для 422 — ``fields``).
    """

    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Единый формат ошибок: ``{"error": {...}}``."""

    error: ErrorBody
