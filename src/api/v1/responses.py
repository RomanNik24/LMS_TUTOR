"""Описание кодов ошибок для OpenAPI (docs/06 A6: модели для всех кодов ответа)."""

from typing import Any

from src.schemas.errors import ErrorResponse

_DESCRIPTIONS: dict[int, str] = {
    400: "Нарушено бизнес-правило",
    401: "Нет или истекла сессия / неверные данные входа",
    403: "Нет прав",
    404: "Не найдено",
    409: "Конфликт состояния",
    422: "Ошибка валидации (details.fields)",
    429: "Превышен лимит запросов",
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Собрать ``responses`` для декоратора эндпоинта с моделью ``ErrorResponse``."""
    return {code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]} for code in codes}
