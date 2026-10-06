"""Юнит-тесты перечислений (задача T1.01).

Значения должны совпадать со строками ENUM-колонок `docs/04_database_schema.md`
(строка -> ожидаемый набор значений). Подход хранения — VARCHAR + CHECK
(`docs/adr/0003-enum-strategy.md`), поэтому в Python значения — обычные строки.
"""

from enum import StrEnum

import pytest
from src.core import enums
from src.core.enums import values

# Каждой ENUM-колонке docs/04 соответствует класс и точный набор значений.
ENUM_CONTRACTS: tuple[tuple[type[StrEnum], str, set[str]], ...] = (
    (enums.ExamKind, "exam_types.kind", {"oge", "ege"}),
    (enums.ExamResultKind, "exam_types.result_kind", {"grade_2_5", "test_100"}),
    (enums.UserRole, "users.role", {"owner", "manager", "student"}),
    (enums.AuthTokenPurpose, "auth_tokens.purpose", {"invite", "web_login"}),
    (enums.LessonStatus, "lessons.status", {"scheduled", "completed", "cancelled"}),
    (
        enums.AttendanceStatus,
        "lesson_participants.attendance",
        {"pending", "attended", "no_show", "cancelled"},
    ),
    (enums.HomeworkKind, "homeworks.kind", {"regular", "mock_exam"}),
    (enums.DueMode, "homeworks.due_mode", {"next_lesson", "fixed"}),
    (
        enums.AssignmentStatus,
        "homework_assignments.status",
        {"assigned", "submitted", "needs_revision", "graded", "expired"},
    ),
    (enums.SubmissionType, "homework_assignments.submission_type", {"files", "self_reported"}),
    (
        enums.HomeworkFileRole,
        "homework_files.role",
        {"student_solution", "teacher_review"},
    ),
    (
        enums.NotificationStatus,
        "notifications.status",
        {"pending", "sent", "failed", "skipped"},
    ),
)


@pytest.mark.parametrize(
    ("enum_cls", "column", "expected"),
    ENUM_CONTRACTS,
    ids=[column for _, column, _ in ENUM_CONTRACTS],
)
def test_enum_values_match_database_schema(
    enum_cls: type[StrEnum], column: str, expected: set[str]
) -> None:
    """Набор значений enum == списку из docs/04 для соответствующей колонки."""
    assert set(values(enum_cls)) == expected


@pytest.mark.parametrize(
    ("enum_cls", "column", "expected"), ENUM_CONTRACTS, ids=[c for _, c, _ in ENUM_CONTRACTS]
)
def test_enum_members_are_strings(enum_cls: type[StrEnum], column: str, expected: set[str]) -> None:
    """Стратегия ADR 0003: значения — строки (VARCHAR), не PostgreSQL-native ENUM."""
    for member in enum_cls:
        assert isinstance(member.value, str)
        assert member == member.value  # StrEnum сравнивается со строкой напрямую


def test_values_returns_declaration_order_tuple() -> None:
    """values() возвращает кортеж в порядке объявления (стабилен для CHECK)."""
    result = values(enums.UserRole)

    assert isinstance(result, tuple)
    assert result == ("owner", "manager", "student")


def test_no_native_pg_enum_markers_in_module() -> None:
    """Модуль не содержит ссылок на native_enum=True / pg ENUM (ADR 0003)."""
    source = open(enums.__file__, encoding="utf-8").read()

    assert "native_enum=True" not in source
    assert "postgresql.ENUM" not in source
