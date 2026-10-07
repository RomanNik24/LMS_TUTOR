"""Схема переноса дедлайна (T4.09)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.schemas.homework import ExtendRequest


def test_body_is_optional() -> None:
    assert ExtendRequest().due_at is None


def test_manual_due_must_be_aware_and_no_other_fields() -> None:
    aware = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    assert ExtendRequest(due_at=aware).due_at == aware
    with pytest.raises(ValidationError):
        ExtendRequest(due_at=datetime(2030, 1, 1, 12, 0))  # noqa: DTZ001
    with pytest.raises(ValidationError):
        ExtendRequest.model_validate({"extensions_count": 0})
