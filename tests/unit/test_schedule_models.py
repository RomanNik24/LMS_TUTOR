"""Схемные тесты моделей расписания и уроков (T3.01, docs/04 §3–§4)."""

from sqlalchemy import CheckConstraint, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import BIGINT, VARCHAR, ExcludeConstraint
from src.core.enums import AttendanceStatus, LessonStatus
from src.db import Base


def table_of(name: str) -> Table:
    return Base.metadata.tables[name]


def check_names(name: str) -> set[str]:
    return {
        str(c.name) for c in table_of(name).constraints if isinstance(c, CheckConstraint) and c.name
    }


def test_schedule_templates_columns_and_checks() -> None:
    table = table_of("schedule_templates")
    assert set(table.c.keys()) == {
        "id",
        "teacher_id",
        "subject_id",
        "weekday",
        "start_local_time",
        "duration_minutes",
        "timezone",
        "starts_on",
        "ends_on",
        "is_active",
        "generated_until",
        "created_at",
        "updated_at",
    }
    assert isinstance(table.c.id.type, BIGINT)
    assert table.c.id.identity is not None
    assert table.c.timezone.type.length == 64
    assert table.c.ends_on.nullable is True
    assert table.c.generated_until.nullable is True
    assert table.c.duration_minutes.server_default is not None
    assert check_names("schedule_templates") == {
        "ck_schedule_templates_weekday_range",
        "ck_schedule_templates_duration_positive",
    }


def test_template_participants_composite_pk_cascade() -> None:
    table = table_of("schedule_template_participants")
    assert list(table.primary_key.columns.keys()) == ["template_id", "student_id"]
    (fk,) = table.c.template_id.foreign_keys
    assert (fk.target_fullname, fk.ondelete) == ("schedule_templates.id", "CASCADE")
    assert "created_at" not in table.c


def test_lessons_columns_constraints_and_indexes() -> None:
    table = table_of("lessons")
    for name in ("video_url_override", "board_url_override"):
        assert isinstance(table.c[name].type, VARCHAR)
        assert table.c[name].type.length == 500
    assert table.c.topic.type.length == 255
    assert table.c.cancel_reason.type.length == 255
    assert table.c.is_detached.server_default is not None
    assert table.c.template_id.nullable is True
    assert {fk.ondelete for fk in table.c.template_id.foreign_keys} == {"SET NULL"}
    assert {fk.ondelete for fk in table.c.cancelled_by.foreign_keys} == {"SET NULL"}
    assert {"ck_lessons_end_after_start", "ck_lessons_status"} <= check_names("lessons")
    uniques = [
        tuple(c.columns.keys()) for c in table.constraints if isinstance(c, UniqueConstraint)
    ]
    assert ("template_id", "start_at") in uniques
    excludes = [c for c in table.constraints if isinstance(c, ExcludeConstraint)]
    assert [c.name for c in excludes] == ["ex_lessons_teacher_no_overlap"]
    assert excludes[0].using == "gist"
    indexes = {tuple(i.columns.keys()) for i in table.indexes}
    assert {("start_at",), ("teacher_id", "start_at"), ("status", "start_at")} <= indexes


def test_lesson_participants_pk_defaults_and_index() -> None:
    table = table_of("lesson_participants")
    assert list(table.primary_key.columns.keys()) == ["lesson_id", "student_id"]
    (fk,) = table.c.lesson_id.foreign_keys
    assert fk.ondelete == "CASCADE"
    assert table.c.price_snapshot.nullable is True
    assert table.c.attendance.server_default is not None
    assert table.c.is_billable.server_default is not None
    assert "ck_lesson_participants_price_snapshot_nonneg" in check_names("lesson_participants")
    assert ("student_id", "lesson_id") in {tuple(i.columns.keys()) for i in table.indexes}


def test_status_values_match_enums() -> None:
    """Допустимые значения в CHECK берутся из enum-ов проекта (ADR 0003)."""
    lessons = table_of("lessons").c.status.type
    participants = table_of("lesson_participants").c.attendance.type
    assert list(lessons.enums) == [m.value for m in LessonStatus]
    assert list(participants.enums) == [m.value for m in AttendanceStatus]
