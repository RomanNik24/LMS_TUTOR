"""Схема сдачи (T4.07)."""

import pytest
from pydantic import ValidationError
from src.schemas.homework import SubmitRequest


def test_comment_is_optional_and_trimmed() -> None:
    assert SubmitRequest().student_comment is None
    assert SubmitRequest(student_comment="  готово  ").student_comment == "готово"
    assert SubmitRequest(student_comment="   ").student_comment is None


def test_comment_limit_and_unknown_fields() -> None:
    assert SubmitRequest(student_comment="а" * 2000)
    with pytest.raises(ValidationError):
        SubmitRequest(student_comment="а" * 2001)
    with pytest.raises(ValidationError):
        SubmitRequest.model_validate({"score": 13})
