"""Схемные тесты модели notifications (T5.01, docs/04 §7.1)."""

from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, Table
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, VARCHAR
from src.core.enums import NotificationStatus, NotificationType
from src.db import Base


def table() -> Table:
    return Base.metadata.tables["notifications"]


def default_of(column: Column[Any]) -> str:
    """SQL-текст серверного значения по умолчанию."""
    return str(getattr(column.server_default, "arg", None))


def test_columns_and_types() -> None:
    assert set(table().c.keys()) == {
        "id",
        "user_id",
        "type",
        "payload",
        "dedup_key",
        "is_urgent",
        "scheduled_for",
        "status",
        "attempts",
        "sent_at",
        "last_error",
        "created_at",
        "updated_at",
    }
    assert isinstance(table().c.id.type, BIGINT)
    assert isinstance(table().c.payload.type, JSONB)
    assert isinstance(table().c.type.type, VARCHAR)
    assert table().c.type.type.length == 50
    assert table().c.dedup_key.type.length == 200


def test_nullability_and_defaults() -> None:
    columns = table().c
    for name in ("user_id", "type", "payload", "dedup_key", "scheduled_for", "status"):
        assert columns[name].nullable is False, name
    assert columns.sent_at.nullable is True
    assert columns.last_error.nullable is True
    assert default_of(columns.status) == "'pending'"
    assert default_of(columns.attempts) == "0"
    assert default_of(columns.is_urgent) == "false"


def test_dedup_key_is_unique() -> None:
    assert table().c.dedup_key.unique is True


def test_status_check_matches_enum() -> None:
    checks = {
        c.name: str(c.sqltext.compile(compile_kwargs={"literal_binds": True}))
        for c in table().constraints
        if isinstance(c, CheckConstraint)
    }
    sql = checks["ck_notifications_status"]
    for member in NotificationStatus:
        assert f"'{member.value}'" in sql


def test_dispatch_index_and_cascade() -> None:
    indexes = {i.name: [c.name for c in i.columns] for i in table().indexes if isinstance(i, Index)}
    assert indexes["ix_notifications_status_scheduled_for"] == ["status", "scheduled_for"]
    (fk,) = table().c.user_id.foreign_keys
    assert fk.ondelete == "CASCADE"


def test_notification_types_match_docs() -> None:
    assert {member.value for member in NotificationType} == {
        "lesson_reminder",
        "homework_deadline",
        "homework_graded",
        "homework_returned",
        "homework_assigned",
        "lesson_cancelled",
        "lesson_rescheduled",
        "homework_submitted",
        "homework_expired",
        "lesson_unmarked",
        "morning_digest",
        "student_joined",
    }
    assert all(len(member.value) <= 50 for member in NotificationType)
