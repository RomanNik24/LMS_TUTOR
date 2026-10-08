"""Схемные тесты модели mock_exam_results (T6.01, docs/04 §6)."""

from sqlalchemy import CheckConstraint, Index, Table
from sqlalchemy.dialects.postgresql import BIGINT
from src.db import Base


def table() -> Table:
    return Base.metadata.tables["mock_exam_results"]


def test_columns() -> None:
    assert set(table().c.keys()) == {
        "id",
        "student_id",
        "exam_type_id",
        "exam_date",
        "primary_score",
        "max_primary",
        "geometry_score",
        "converted_value",
        "scale_year",
        "assignment_id",
        "comment",
        "created_by",
        "created_at",
        "updated_at",
    }
    assert isinstance(table().c.id.type, BIGINT)
    assert type(table().c.exam_date.type).__name__ == "Date"


def test_nullability() -> None:
    columns = table().c
    required = ("student_id", "exam_type_id", "exam_date", "primary_score", "max_primary")
    for name in (*required, "created_by"):
        assert columns[name].nullable is False, name
    for name in ("geometry_score", "converted_value", "scale_year", "assignment_id", "comment"):
        assert columns[name].nullable is True, name


def test_assignment_link_is_unique_and_set_null() -> None:
    column = table().c.assignment_id
    assert column.unique is True
    (foreign_key,) = column.foreign_keys
    assert foreign_key.target_fullname == "homework_assignments.id"
    assert foreign_key.ondelete == "SET NULL"


def test_other_foreign_keys_restrict() -> None:
    for name, target in (
        ("student_id", "users.id"),
        ("exam_type_id", "exam_types.id"),
        ("created_by", "users.id"),
    ):
        (foreign_key,) = table().c[name].foreign_keys
        assert (foreign_key.target_fullname, foreign_key.ondelete) == (target, "RESTRICT"), name


def test_primary_score_check_and_progress_index() -> None:
    checks = {str(c.sqltext) for c in table().constraints if isinstance(c, CheckConstraint)}
    assert "primary_score >= 0" in checks
    indexes = {tuple(i.columns.keys()) for i in table().indexes if isinstance(i, Index)}
    assert ("student_id", "exam_type_id", "exam_date") in indexes
