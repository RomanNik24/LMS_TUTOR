"""Схемные тесты моделей домашних заданий (T4.01, docs/04 §5)."""

from sqlalchemy import CheckConstraint, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import BIGINT, VARCHAR
from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkFileRole,
    HomeworkKind,
    SubmissionType,
)
from src.db import Base


def table_of(name: str) -> Table:
    return Base.metadata.tables[name]


def checks(name: str) -> set[str]:
    return {
        str(c.name) for c in table_of(name).constraints if isinstance(c, CheckConstraint) and c.name
    }


def ondelete(table: str, column: str) -> str | None:
    (fk,) = table_of(table).c[column].foreign_keys
    return fk.ondelete


def test_homeworks_columns_and_checks() -> None:
    table = table_of("homeworks")
    assert set(table.c.keys()) == {
        "id",
        "created_by",
        "lesson_id",
        "subject_id",
        "kind",
        "exam_type_id",
        "title",
        "description",
        "max_score",
        "due_mode",
        "created_at",
        "updated_at",
    }
    assert isinstance(table.c.id.type, BIGINT)
    assert table.c.title.type.length == 200
    assert table.c.exam_type_id.nullable is True
    assert table.c.lesson_id.nullable is True
    assert ondelete("homeworks", "lesson_id") == "SET NULL"
    assert checks("homeworks") >= {
        "ck_homeworks_max_score_positive",
        "ck_homeworks_mock_exam_needs_exam_type",
        "ck_homeworks_kind",
        "ck_homeworks_due_mode",
    }


def test_materials_have_no_timestamps_and_cascade() -> None:
    table = table_of("homework_materials")
    assert set(table.c.keys()) == {
        "id",
        "homework_id",
        "s3_key",
        "original_name",
        "content_type",
        "size_bytes",
    }
    assert table.c.s3_key.type.length == 500
    assert ondelete("homework_materials", "homework_id") == "CASCADE"


def test_assignments_columns_defaults_and_constraints() -> None:
    table = table_of("homework_assignments")
    for name in (
        "status",
        "original_due_at",
        "due_at",
        "extensions_count",
        "submission_type",
        "submitted_at",
        "score",
        "graded_at",
        "graded_by",
        "graded_after_expiry",
        "teacher_comment",
        "student_comment",
        "expired_at",
    ):
        assert name in table.c, name
    assert table.c.status.server_default is not None
    assert table.c.extensions_count.server_default is not None
    assert table.c.graded_after_expiry.server_default is not None
    assert table.c.submission_type.nullable is True
    assert table.c.score.nullable is True
    assert ondelete("homework_assignments", "homework_id") == "CASCADE"
    assert ondelete("homework_assignments", "graded_by") == "SET NULL"
    uniques = [
        tuple(c.columns.keys()) for c in table.constraints if isinstance(c, UniqueConstraint)
    ]
    assert ("homework_id", "student_id") in uniques
    assert checks("homework_assignments") >= {
        "ck_homework_assignments_extensions_count_range",
        "ck_homework_assignments_score_nonneg",
        "ck_homework_assignments_status",
        "ck_homework_assignments_submission_type",
    }
    indexes = {tuple(i.columns.keys()) for i in table.indexes}
    assert {("student_id", "status"), ("status", "due_at")} <= indexes


def test_extensions_journal_has_only_created_at() -> None:
    table = table_of("homework_extensions")
    assert set(table.c.keys()) == {
        "id",
        "assignment_id",
        "old_due_at",
        "new_due_at",
        "created_by",
        "created_at",
    }
    assert ondelete("homework_extensions", "assignment_id") == "CASCADE"


def test_files_columns_and_cascade() -> None:
    table = table_of("homework_files")
    assert set(table.c.keys()) == {
        "id",
        "assignment_id",
        "uploaded_by",
        "role",
        "s3_key",
        "original_name",
        "content_type",
        "size_bytes",
        "created_at",
    }
    assert isinstance(table.c.original_name.type, VARCHAR)
    assert table.c.original_name.type.length == 255
    assert table.c.content_type.type.length == 100
    assert ondelete("homework_files", "assignment_id") == "CASCADE"
    assert "ck_homework_files_role" in checks("homework_files")


def test_enum_values_match_project_enums() -> None:
    expected = {
        ("homeworks", "kind"): HomeworkKind,
        ("homeworks", "due_mode"): DueMode,
        ("homework_assignments", "status"): AssignmentStatus,
        ("homework_assignments", "submission_type"): SubmissionType,
        ("homework_files", "role"): HomeworkFileRole,
    }
    for (table, column), enum_cls in expected.items():
        assert list(table_of(table).c[column].type.enums) == [m.value for m in enum_cls]


def test_fk_lookup_indexes_exist() -> None:
    """Аудит 2026-10-08, п. 9: файлы, журнал переносов и материалы выбираются по FK."""
    from src.db.models import HomeworkExtension, HomeworkFile, HomeworkMaterial  # noqa: PLC0415

    for model, column in (
        (HomeworkFile, "assignment_id"),
        (HomeworkExtension, "assignment_id"),
        (HomeworkMaterial, "homework_id"),
    ):
        assert (column,) in {tuple(i.columns.keys()) for i in model.__table__.indexes}
