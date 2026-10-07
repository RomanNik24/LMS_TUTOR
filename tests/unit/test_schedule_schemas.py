"""Схема создания урока (T3.04): время, участники, ссылки."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from src.schemas.schedule import LESSON_MAX_PARTICIPANTS, LessonCreate

START = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


def make(**patch: object) -> LessonCreate:
    base: dict[str, object] = {
        "subject_code": "informatics",
        "student_ids": [1],
        "start_at": START,
        "end_at": START + timedelta(hours=1),
    }
    return LessonCreate.model_validate(base | patch)


def test_valid_lesson_and_defaults() -> None:
    lesson = make()
    assert lesson.teacher_id is None
    assert lesson.topic is None
    assert lesson.video_url_override is None


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(start_at=datetime(2026, 10, 12, 14, 0), end_at=datetime(2026, 10, 12, 15, 0))  # noqa: DTZ001


@pytest.mark.parametrize("minutes", [0, -30])
def test_end_must_be_after_start(minutes: int) -> None:
    with pytest.raises(ValidationError):
        make(end_at=START + timedelta(minutes=minutes))


def test_lesson_length_limit_is_12_hours() -> None:
    make(end_at=START + timedelta(hours=12))
    with pytest.raises(ValidationError):
        make(end_at=START + timedelta(hours=12, minutes=1))


def test_participants_limits_and_duplicates() -> None:
    with pytest.raises(ValidationError):
        make(student_ids=[])
    with pytest.raises(ValidationError):
        make(student_ids=[1, 1])
    make(student_ids=list(range(1, LESSON_MAX_PARTICIPANTS + 1)))
    with pytest.raises(ValidationError):
        make(student_ids=list(range(1, LESSON_MAX_PARTICIPANTS + 2)))


def test_urls_must_be_https_and_empty_means_none() -> None:
    assert make(video_url_override="  ").video_url_override is None
    assert make(board_url_override="https://miro.com/b/1").board_url_override
    with pytest.raises(ValidationError):
        make(video_url_override="http://example.com")


def test_topic_is_trimmed_and_limited() -> None:
    assert make(topic="  Графы  ").topic == "Графы"
    assert make(topic="   ").topic is None
    with pytest.raises(ValidationError):
        make(topic="а" * 256)


def test_unknown_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        make(price=100)


# ---------------------------------------------------------------- перенос, отмена, отметка (T3.05)


def test_reschedule_checks_interval() -> None:
    from src.schemas.schedule import LessonReschedule  # noqa: PLC0415

    LessonReschedule(start_at=START, end_at=START + timedelta(hours=1))
    with pytest.raises(ValidationError):
        LessonReschedule(start_at=START, end_at=START)


def test_cancel_reason_is_trimmed_limited_and_ids_unique() -> None:
    from src.schemas.schedule import LessonCancel  # noqa: PLC0415

    assert LessonCancel(reason="  ").reason is None
    with pytest.raises(ValidationError):
        LessonCancel(reason="а" * 256)
    with pytest.raises(ValidationError):
        LessonCancel(billable_student_ids=[1, 1])


def test_complete_marks_validation() -> None:
    from src.schemas.schedule import LessonComplete  # noqa: PLC0415

    ok = LessonComplete.model_validate({"marks": [{"student_id": 1, "attendance": "attended"}]})
    assert ok.marks[0].is_billable is None
    for bad in (
        {"marks": []},
        {"marks": [{"student_id": 1, "attendance": "pending"}]},
        {
            "marks": [
                {"student_id": 1, "attendance": "attended"},
                {"student_id": 1, "attendance": "no_show"},
            ]
        },
    ):
        with pytest.raises(ValidationError):
            LessonComplete.model_validate(bad)
