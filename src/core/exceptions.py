"""Кастомные исключения приложения MY_LMS (задача T1.01).

Соответствуют `docs/03` §11 и `docs/06` A5: весь прикладной код бросает
только классы из этого модуля. HTTP-коды и смысл кодов ошибок — по
`docs/08` §1 («Формат ошибок»).

Поля:
- `code` — машинночитаемый код для клиента (snake_case);
- `message` — человекочитаемое сообщение (русский);
- `details` — дополнительные данные (например, `fields` для 422);
- `http_status` — HTTP-код ответа, который вернёт обработчик FastAPI.
"""

from collections.abc import Mapping, Sequence
from typing import Union

from src.core import texts

# Тип значения в `details`: JSON-совместимое произвольное значение.
# Вводится псевдоним (а не `Any`), чтобы прикладной код и тесты не
# использовали `Any` напрямую (требование задач: «any не использовать»).
DetailValue = Union[  # noqa: UP007 - union нужен рекурсивным с forward-ссылкой
    str,
    int,
    float,
    bool,
    None,
    Sequence["DetailValue"],
    Mapping[str, "DetailValue"],
]


class AppError(Exception):
    """Базовая прикладная ошибка приложения.

    Непосредственно не бросается: используются наследники либо экземпляр
    с явным `code`/`http_status` (например, 401 `unauthenticated`).

    Attributes:
        code: Машинночитаемый код ошибки (docs/08 §1).
        message: Человекочитаемое сообщение для клиента.
        details: Дополнительные данные об ошибке.
        http_status: HTTP-код ответа.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        details: dict[str, DetailValue] | None = None,
        http_status: int = 500,
    ) -> None:
        """Создать ошибку.

        Args:
            message: Человекочитаемое сообщение для клиента.
            code: Машинночитаемый код ошибки; по умолчанию `internal_error`.
            details: Данные об ошибке; `None` нормализуется в `{}`.
            http_status: HTTP-код ответа; по умолчанию 500.
        """
        self.code: str = code
        self.message: str = message
        self.details: dict[str, DetailValue] = {} if details is None else details
        self.http_status: int = http_status
        super().__init__(message)


class NotFoundError(AppError):
    """Ресурс не найден (HTTP 404, код `not_found`, docs/08 §1).

    Для данных, к которым у ученика нет доступа, по docs/08 §1 тоже
    возвращается 404 (не раскрываем существование объекта).
    """

    def __init__(
        self,
        message: str = texts.API_NOT_FOUND_DEFAULT,
        *,
        code: str = "not_found",
        details: dict[str, DetailValue] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=404)


class PermissionDeniedError(AppError):
    """Нет прав на действие (HTTP 403, код `permission_denied`, docs/08 §1)."""

    def __init__(
        self,
        message: str = texts.API_PERMISSION_DENIED,
        *,
        code: str = "permission_denied",
        details: dict[str, DetailValue] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=403)


class ValidationError(AppError):
    """Ошибка валидации схемы/полей (HTTP 422, код `validation_error`, docs/08 §1).

    В `details` по docs/08 передаётся ключ `fields`.
    """

    def __init__(
        self,
        message: str = texts.API_VALIDATION_FAILED,
        *,
        code: str = "validation_error",
        details: dict[str, DetailValue] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=422)


class ConflictError(AppError):
    """Конфликт состояния (HTTP 409, docs/08 §1).

    Конкретный код (`lesson_overlap`, `invite_already_used`,
    `telegram_already_linked`, ...) передаётся при создании экземпляра.
    """

    def __init__(
        self,
        message: str = texts.API_CONFLICT_DEFAULT,
        *,
        code: str = "conflict",
        details: dict[str, DetailValue] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=409)


class BusinessRuleError(AppError):
    """Нарушено бизнес-правило (HTTP 400, docs/08 §1).

    Конкретный код (`homework_extension_limit`, `score_out_of_range`, ...)
    передаётся при создании экземпляра.
    """

    def __init__(
        self,
        message: str = texts.API_BUSINESS_RULE_DEFAULT,
        *,
        code: str = "business_rule_violation",
        details: dict[str, DetailValue] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=400)


class ExternalServiceError(AppError):
    """Сбой внешнего сервиса (Telegram API, S3) — docs/03 §11, docs/06 A5.

    Единый контракт ошибок — docs/08 §1: публичный HTTP 502 и отдельный код
    в документации не определены, поэтому клиент получает документированные
    500 ``internal_error`` с нейтральным сообщением.
    Сообщение клиенту нейтральное: внутренние детали стороннего сервиса
    наружу не отдаём.
    """

    def __init__(
        self,
        message: str = "Внешний сервис временно недоступен. Попробуйте позже.",
        *,
        code: str = "internal_error",
        details: dict[str, DetailValue] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, http_status=500)
