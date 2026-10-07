"""Схемы шаблонов расписания (T3.06)."""

from datetime import date, time

import pytest
from pydantic import ValidationError
from src.schemas.schedule import TemplateCreate, TemplateUpdate


def make(**patch: object) -> TemplateCreate:
    base: dict[str, object] = {
        "subject_code": "informatics",
        "student_ids": [1],
        "weekday": 2,
        "start_local_time": time(17, 0),
        "starts_on": date(2026, 10, 6),
    }
    return TemplateCreate.model_validate(base | patch)


def test_defaults() -> None:
    template = make()
    assert template.duration_minutes == 60
    assert template.timezone == "Europe/Moscow"
    assert template.ends_on is None


@pytest.mark.parametrize("weekday", [0, 8])
def test_weekday_range(weekday: int) -> None:
    with pytest.raises(ValidationError):
        make(weekday=weekday)


def test_duration_limits() -> None:
    make(duration_minutes=1)
    make(duration_minutes=720)
    for bad in (0, 721):
        with pytest.raises(ValidationError):
            make(duration_minutes=bad)


def test_period_and_timezone_and_time() -> None:
    make(ends_on=date(2026, 10, 6))
    with pytest.raises(ValidationError):
        make(ends_on=date(2026, 10, 5))
    with pytest.raises(ValidationError):
        make(timezone="Mars/Base")
    with pytest.raises(ValidationError):
        make(start_local_time="17:00:00+03:00")


def test_participants_rules() -> None:
    with pytest.raises(ValidationError):
        make(student_ids=[])
    with pytest.raises(ValidationError):
        make(student_ids=[1, 1])


def test_update_requires_a_field_and_forbids_nulls() -> None:
    with pytest.raises(ValidationError):
        TemplateUpdate.model_validate({})
    for name in ("weekday", "start_local_time", "timezone", "starts_on", "is_active"):
        with pytest.raises(ValidationError):
            TemplateUpdate.model_validate({name: None})
    cleared = TemplateUpdate.model_validate({"ends_on": None})
    assert "ends_on" in cleared.model_fields_set
    assert cleared.ends_on is None


def test_update_validates_fields() -> None:
    assert TemplateUpdate.model_validate({"weekday": 7}).weekday == 7
    with pytest.raises(ValidationError):
        TemplateUpdate.model_validate({"weekday": 9})
    with pytest.raises(ValidationError):
        TemplateUpdate.model_validate({"timezone": "Nope/Zone"})
    with pytest.raises(ValidationError):
        TemplateUpdate.model_validate({"student_ids": [2, 2]})
