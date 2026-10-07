"""Схемы создания задания (T4.06)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.schemas.homework import AssigneesAdd, HomeworkCreate

DUE = datetime(2030, 10, 14, 14, 0, tzinfo=UTC)


def make(**patch: object) -> HomeworkCreate:
    base: dict[str, object] = {
        "kind": "regular",
        "title": "Графы",
        "subject_code": "informatics",
        "max_score": 13,
        "due_mode": "fixed",
        "due_at": DUE,
        "student_ids": [1],
    }
    return HomeworkCreate.model_validate(base | patch)


def test_valid_regular_homework() -> None:
    homework = make(title="  Графы  ", description="  ")
    assert homework.title == "Графы"
    assert homework.description is None


def test_mock_exam_requires_exam_type() -> None:
    with pytest.raises(ValidationError):
        make(kind="mock_exam", exam_type_id=None)
    exam = make(kind="mock_exam", exam_type_id=3, subject_code=None, max_score=None)
    assert exam.exam_type_id == 3


def test_regular_requires_subject_and_max_score() -> None:
    with pytest.raises(ValidationError):
        make(subject_code=None)
    with pytest.raises(ValidationError):
        make(max_score=None)


@pytest.mark.parametrize("score", [0, -1, 201])
def test_max_score_bounds(score: int) -> None:
    with pytest.raises(ValidationError):
        make(max_score=score)


def test_max_score_edges_are_allowed() -> None:
    assert make(max_score=1).max_score == 1
    assert make(max_score=200).max_score == 200


def test_fixed_requires_due_at_but_next_lesson_does_not() -> None:
    with pytest.raises(ValidationError):
        make(due_mode="fixed", due_at=None)
    assert make(due_mode="next_lesson", due_at=None).due_at is None


def test_naive_due_at_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(due_at=datetime(2030, 10, 14, 14, 0))  # noqa: DTZ001


def test_title_and_students_rules() -> None:
    for patch in (
        {"title": ""},
        {"title": "   "},
        {"title": "а" * 201},
        {"student_ids": []},
        {"student_ids": [1, 1]},
        {"student_ids": list(range(1, 102))},
        {"unknown": 1},
    ):
        with pytest.raises(ValidationError):
            make(**patch)
    assert make(title="а" * 200)


def test_assignees_add_rules() -> None:
    assert AssigneesAdd(student_ids=[1, 2]).due_at is None
    with pytest.raises(ValidationError):
        AssigneesAdd(student_ids=[])
    with pytest.raises(ValidationError):
        AssigneesAdd(student_ids=[3, 3])
