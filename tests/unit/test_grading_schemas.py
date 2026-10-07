"""Схемы оценки и возврата (T4.08)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.schemas.homework import GradeRequest, ReturnRequest


def test_grade_comment_is_optional_and_trimmed() -> None:
    assert GradeRequest(score=11).comment is None
    assert GradeRequest(score=11, comment="  Молодец  ").comment == "Молодец"
    assert GradeRequest(score=11, comment="  ").comment is None


def test_grade_score_must_be_integer_but_range_is_checked_by_service() -> None:
    assert GradeRequest(score=-5).score == -5  # границу 0..max проверяет сервис (400)
    with pytest.raises(ValidationError):
        GradeRequest.model_validate({"score": "много"})
    with pytest.raises(ValidationError):
        GradeRequest.model_validate({"score": 10.5})


def test_return_requires_comment() -> None:
    assert ReturnRequest(comment="Исправьте задачу 3").new_due_at is None
    for bad in ("", "   "):
        with pytest.raises(ValidationError):
            ReturnRequest(comment=bad)


def test_return_due_must_be_aware() -> None:
    aware = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    assert ReturnRequest(comment="ок", new_due_at=aware).new_due_at == aware
    with pytest.raises(ValidationError):
        ReturnRequest(comment="ок", new_due_at=datetime(2030, 1, 1, 12, 0))  # noqa: DTZ001
