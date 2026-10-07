"""Схемы запросов по ученикам (T2.02): ссылки только https, пустое изменение, null-поля."""

import pytest
from pydantic import ValidationError
from src.schemas.students import StudentCreate, StudentUpdate


def test_create_defaults_and_trimming() -> None:
    student = StudentCreate(display_name="  Аня  ")
    assert student.display_name == "Аня"
    assert student.timezone == "Europe/Moscow"
    assert student.lesson_price is None
    assert student.subject_codes == []


@pytest.mark.parametrize("field", ["video_url", "board_url"])
@pytest.mark.parametrize(
    "url",
    ["http://meet.example.com/x", "ftp://x.example.com", "javascript:alert(1)", "meet.example"],
)
def test_non_https_link_is_rejected(field: str, url: str) -> None:
    with pytest.raises(ValidationError):
        StudentCreate(display_name="Аня", **{field: url})
    with pytest.raises(ValidationError):
        StudentUpdate(**{field: url})


def test_https_link_is_accepted_and_blank_clears_it() -> None:
    assert StudentCreate(
        display_name="А", video_url=" https://telemost.yandex.ru/j/1 "
    ).video_url == ("https://telemost.yandex.ru/j/1")
    assert StudentCreate(display_name="А", video_url="   ").video_url is None


def test_create_rejects_unknown_timezone_negative_price_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StudentCreate(display_name="А", timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        StudentCreate(display_name="А", lesson_price=-1)
    with pytest.raises(ValidationError):
        StudentCreate(display_name="А", school_class=12)
    with pytest.raises(ValidationError):
        StudentCreate.model_validate({"display_name": "А", "role": "owner"})


def test_update_requires_at_least_one_field() -> None:
    with pytest.raises(ValidationError):
        StudentUpdate()


def test_update_null_clears_optional_but_not_required_fields() -> None:
    cleared = StudentUpdate.model_validate({"video_url": None, "teacher_notes": None})
    assert cleared.model_fields_set == {"video_url", "teacher_notes"}
    for name in ("display_name", "timezone", "subject_codes", "lesson_price", "teacher_id"):
        with pytest.raises(ValidationError):
            StudentUpdate.model_validate({name: None})


def test_update_tracks_only_passed_fields() -> None:
    update = StudentUpdate(lesson_price=1500)
    assert update.model_fields_set == {"lesson_price"}
