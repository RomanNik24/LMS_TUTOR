"""Юнит-тесты прикладных исключений (задача T1.01).

Проверяют общий набор полей `code/message/details/http_status` и соответствие
кодов HTTP таблице docs/08 §1.
"""

from src.core.exceptions import (
    AppError,
    BusinessRuleError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
)
from src.core.exceptions import ValidationError as AppValidationError

# Все прикладные подклассы: ни один не должен вводить статус вне docs/08 §1.
_ALL_APP_ERRORS = (
    NotFoundError,
    PermissionDeniedError,
    AppValidationError,
    ConflictError,
    BusinessRuleError,
    ExternalServiceError,
)


def test_app_error_base_fields() -> None:
    """Базовый `AppError` несёт code, message, details и http_status."""
    error = AppError("Сломалось", code="custom_code", details={"a": 1}, http_status=418)

    assert error.code == "custom_code"
    assert error.message == "Сломалось"
    assert error.details == {"a": 1}
    assert error.http_status == 418
    assert isinstance(error, Exception)


def test_app_error_details_defaults_to_empty_dict() -> None:
    """`details=None` нормализуется в пустой словарь (всегда объект в JSON)."""
    assert AppError("x").details == {}


def test_not_found_error() -> None:
    """NotFoundError → 404 / `not_found` (docs/08 §1)."""
    error = NotFoundError("Урок не найден.")

    assert (error.http_status, error.code) == (404, "not_found")
    assert error.message == "Урок не найден."


def test_permission_denied_error() -> None:
    """PermissionDeniedError → 403 / `permission_denied`."""
    error = PermissionDeniedError()

    assert (error.http_status, error.code) == (403, "permission_denied")


def test_validation_error() -> None:
    """ValidationError → 422 / `validation_error`, details.fields по docs/08."""
    error = AppValidationError(details={"fields": [{"field": "email", "message": "bad"}]})

    assert (error.http_status, error.code) == (422, "validation_error")
    assert error.details["fields"][0]["field"] == "email"


def test_conflict_error_allows_specific_code() -> None:
    """ConflictError → 409; конкретный код задаётся экземпляром."""
    error = ConflictError(code="invite_already_used")

    assert (error.http_status, error.code) == (409, "invite_already_used")


def test_business_rule_error() -> None:
    """BusinessRuleError → 400 (нарушение бизнес-правила, docs/08 §1)."""
    error = BusinessRuleError(code="lesson_overlap")

    assert (error.http_status, error.code) == (400, "lesson_overlap")


def test_external_service_error() -> None:
    """ExternalServiceError → документированный 500 (docs/08 §1; 502 не вводим)."""
    error = ExternalServiceError()

    assert (error.http_status, error.code) == (500, "external_service_error")
    # Публичный HTTP 502 не вводим: контракт — только статусы docs/08 §1.
    assert all(cls().http_status != 502 for cls in _ALL_APP_ERRORS)


def test_all_errors_inherit_app_error() -> None:
    """Все классы — наследники AppError: единая точка перехвата в FastAPI."""
    for cls in (
        NotFoundError,
        PermissionDeniedError,
        AppValidationError,
        ConflictError,
        BusinessRuleError,
        ExternalServiceError,
    ):
        assert issubclass(cls, AppError)
