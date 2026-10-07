"""Схемные юнит-тесты SQLAlchemy-моделей ядра БД (задача T1.02).

Сверяют таблицы, колонки и связи ``src/db/models/`` с единственным
источником схемы — ``docs/04_database_schema.md`` (разделы §0, §1.1–1.3,
§2 и §7.2).

Модели реально импортируются из пакета ``src.db``: этот файл падает, если
модели нельзя собрать на текущем Python или если mapper-конфигурация
SQLAlchemy завершается ошибкой.
"""

from __future__ import annotations

import importlib
from enum import StrEnum

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    SmallInteger,
    Table,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, CHAR, JSONB, VARCHAR
from sqlalchemy.dialects.postgresql import ENUM as PostgresEnum
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable
from src.core.enums import AuthTokenPurpose, ExamKind, ExamResultKind, UserRole
from src.db import Base
from src.db.models import (
    AuditLog,
    AuthToken,
    ExamType,
    GradeScale,
    Guardian,
    StudentProfile,
    StudentSubject,
    Subject,
    User,
)

EXPECTED_TABLES: set[str] = {
    "subjects",
    "exam_types",
    "grade_scales",
    "users",
    "student_profiles",
    "student_subjects",
    "guardians",
    "auth_tokens",
    "audit_log",
    "schedule_templates",
    "schedule_template_participants",
    "lessons",
    "lesson_participants",
}

IDENTITY_PK_TABLES = (
    "subjects",
    "exam_types",
    "grade_scales",
    "users",
    "guardians",
    "auth_tokens",
    "audit_log",
)

TIMESTAMPED_TABLES = (
    "subjects",
    "exam_types",
    "grade_scales",
    "users",
    "student_profiles",
    "guardians",
    "auth_tokens",
)

ALL_MODELS = (
    Subject,
    ExamType,
    GradeScale,
    User,
    StudentProfile,
    StudentSubject,
    Guardian,
    AuthToken,
    AuditLog,
)

FOREIGN_KEYS = (
    ("exam_types", "subject_id", "subjects.id", "RESTRICT"),
    ("grade_scales", "exam_type_id", "exam_types.id", "CASCADE"),
    ("student_profiles", "user_id", "users.id", "CASCADE"),
    ("student_profiles", "teacher_id", "users.id", "RESTRICT"),
    ("student_subjects", "student_id", "users.id", "CASCADE"),
    ("student_subjects", "subject_id", "subjects.id", "CASCADE"),
    ("guardians", "student_id", "users.id", "CASCADE"),
    ("guardians", "user_id", "users.id", "SET NULL"),
    ("auth_tokens", "user_id", "users.id", "CASCADE"),
    ("auth_tokens", "created_by", "users.id", "SET NULL"),
    ("audit_log", "actor_user_id", "users.id", "SET NULL"),
)

ENUM_COLUMNS = (
    ("exam_types", "kind", ExamKind),
    ("exam_types", "result_kind", ExamResultKind),
    ("users", "role", UserRole),
    ("auth_tokens", "purpose", AuthTokenPurpose),
)


def table_of(name: str) -> Table:
    """Возвращает Table по имени."""

    return Base.metadata.tables[name]


def col_of(table_name: str, column_name: str) -> Column:
    """Возвращает Column по имени таблицы и колонки."""

    return table_of(table_name).c[column_name]


def unique_sets(tablename: str) -> list[frozenset[str]]:
    """Наборы колонок всех UNIQUE-ограничений таблицы."""

    return [
        frozenset(constraint.columns.keys())
        for constraint in table_of(tablename).constraints
        if isinstance(constraint, UniqueConstraint)
    ]


def server_default_text(table_name: str, column_name: str) -> str | None:
    """Текст server_default-функции, либо None."""

    arg = col_of(table_name, column_name).server_default.arg
    return getattr(arg, "text", None)


def test_all_tables_of_phase_exist_and_no_future_tables() -> None:
    """Набор таблиц ровно такой, как в EXPECTED_TABLES: из будущих этапов ничего не добавлено."""

    assert set(Base.metadata.tables) == EXPECTED_TABLES


@pytest.mark.parametrize("tablename", IDENTITY_PK_TABLES, ids=IDENTITY_PK_TABLES)
def test_id_bigint_generated_always_identity(tablename: str) -> None:
    """PK id: BIGINT GENERATED ALWAYS AS IDENTITY (docs/04 §0)."""

    id_col = col_of(tablename, "id")
    assert id_col.primary_key is True
    assert isinstance(id_col.type, BIGINT)
    assert id_col.nullable is False
    assert id_col.identity is not None
    assert id_col.identity.always is True


def test_student_profiles_pk_is_user_id() -> None:
    """Профиль ученика: PK = user_id, 1:1 с users."""

    assert list(table_of("student_profiles").primary_key.columns.keys()) == ["user_id"]
    user_id = col_of("student_profiles", "user_id")
    assert isinstance(user_id.type, BIGINT)
    assert user_id.identity is None
    (fk,) = user_id.foreign_keys
    assert fk.target_fullname == "users.id"
    assert fk.ondelete == "CASCADE"


def test_student_subjects_composite_pk_and_no_timestamps() -> None:
    """Связующая таблица: составной PK, временных колонок нет."""

    keys = set(table_of("student_subjects").primary_key.columns.keys())
    assert keys == {"student_id", "subject_id"}
    assert "created_at" not in table_of("student_subjects").c
    assert "updated_at" not in table_of("student_subjects").c


def test_subjects_columns() -> None:
    """Колонки subjects."""

    assert set(table_of("subjects").c.keys()) == {
        "id",
        "code",
        "name",
        "is_active",
        "created_at",
        "updated_at",
    }
    code = col_of("subjects", "code")
    assert isinstance(code.type, VARCHAR)
    assert code.type.length == 32
    assert code.nullable is False
    name = col_of("subjects", "name")
    assert isinstance(name.type, VARCHAR)
    assert name.type.length == 100
    assert name.nullable is False
    is_active = col_of("subjects", "is_active")
    assert isinstance(is_active.type, BOOLEAN)
    assert is_active.nullable is False
    assert is_active.server_default is not None


def test_unique_constraints_in_doc() -> None:
    """UNIQUE-ограничения, заданные в docs/04."""

    assert frozenset({"code"}) in unique_sets("subjects")
    assert frozenset({"code"}) in unique_sets("exam_types")
    assert frozenset({"telegram_id"}) in unique_sets("users")
    assert frozenset({"token_hash"}) in unique_sets("auth_tokens")
    assert frozenset({"exam_type_id", "valid_year", "primary_score"}) in unique_sets("grade_scales")


def test_users_telegram_id_nullable_unique() -> None:
    """telegram_id: BIGINT NULL, повторяющиеся NULL допустимы."""

    telegram_id = col_of("users", "telegram_id")
    assert isinstance(telegram_id.type, BIGINT)
    assert telegram_id.nullable is True
    assert telegram_id.unique is True


def test_integral_and_jsonb_types() -> None:
    """Точные типы SMALLINT/INTEGER/JSONB/CHAR."""

    assert isinstance(col_of("exam_types", "max_primary").type, SmallInteger)
    assert isinstance(col_of("grade_scales", "valid_year").type, SmallInteger)
    assert isinstance(col_of("grade_scales", "primary_score").type, SmallInteger)
    assert isinstance(col_of("grade_scales", "result_value").type, SmallInteger)
    assert isinstance(col_of("student_profiles", "school_class").type, SmallInteger)
    assert isinstance(col_of("student_profiles", "lesson_price").type, Integer)
    assert isinstance(col_of("guardians", "telegram_id").type, BIGINT)
    assert isinstance(col_of("audit_log", "entity_id").type, BIGINT)

    config = col_of("exam_types", "config")
    assert isinstance(config.type, JSONB)
    assert config.nullable is False
    assert config.server_default is not None
    data = col_of("audit_log", "data")
    assert isinstance(data.type, JSONB)
    assert data.nullable is False
    assert data.server_default is not None

    token_hash = col_of("auth_tokens", "token_hash")
    assert isinstance(token_hash.type, CHAR)
    assert token_hash.type.length == 64
    assert token_hash.nullable is False
    assert token_hash.unique is True

    assert col_of("audit_log", "action").type.length == 80
    assert col_of("audit_log", "entity_type").type.length == 50


def test_server_defaults_from_doc() -> None:
    """DEFAULT, заданные в docs/04."""

    assert server_default_text("subjects", "is_active") == "true"
    assert server_default_text("users", "is_active") == "true"
    assert server_default_text("users", "bot_blocked") == "false"
    assert server_default_text("users", "timezone") == "'Europe/Moscow'"
    assert server_default_text("student_profiles", "lesson_price") == "0"
    assert server_default_text("exam_types", "config") == "'{}'"
    assert server_default_text("audit_log", "data") == "'{}'"


@pytest.mark.parametrize("tablename", TIMESTAMPED_TABLES, ids=TIMESTAMPED_TABLES)
def test_created_updated_timestamps(tablename: str) -> None:
    """created_at/updated_at: TIMESTAMPTZ NOT NULL DEFAULT now()."""

    for column_name in ("created_at", "updated_at"):
        stamp = col_of(tablename, column_name)
        assert isinstance(stamp.type, DateTime)
        assert stamp.type.timezone is True
        assert stamp.nullable is False
        assert stamp.server_default is not None


def test_audit_log_has_only_created_at() -> None:
    """Журнал: только created_at, без updated_at."""

    assert "created_at" in table_of("audit_log").c
    assert "updated_at" not in table_of("audit_log").c
    created_at = col_of("audit_log", "created_at")
    assert isinstance(created_at.type, DateTime)
    assert created_at.type.timezone is True
    assert created_at.nullable is False
    assert created_at.server_default is not None


def test_users_and_auth_tokens_time_columns() -> None:
    """Точечные TIMESTAMPTZ-колонки с флагами NULL."""

    for column_name in ("archived_at", "last_seen_at"):
        stamp = col_of("users", column_name)
        assert isinstance(stamp.type, DateTime)
        assert stamp.type.timezone is True
        assert stamp.nullable is True

    for column_name, nullable in (
        ("expires_at", False),
        ("used_at", True),
        ("revoked_at", True),
    ):
        stamp = col_of("auth_tokens", column_name)
        assert isinstance(stamp.type, DateTime)
        assert stamp.type.timezone is True
        assert stamp.nullable is nullable


@pytest.mark.parametrize(
    ("tablename", "column_name", "enum_cls"),
    ENUM_COLUMNS,
    ids=[f"{table_name}.{colname}" for table_name, colname, _ in ENUM_COLUMNS],
)
def test_enum_columns_use_non_native_varchar_check(
    tablename: str, column_name: str, enum_cls: type[StrEnum]
) -> None:
    """ENUM: SQLAlchemy Enum, native_enum=False, VARCHAR + CHECK."""

    col = col_of(tablename, column_name)
    assert isinstance(col.type, SqlEnum)
    assert col.type.native_enum is False
    assert col.type.create_constraint is True
    assert col.type.name == column_name
    assert col.type.length == max(len(member.value) for member in enum_cls)
    assert col.type.enums == [member.value for member in enum_cls]
    assert col.nullable is False

    ddl = table_ddl(tablename)
    assert (
        f"CONSTRAINT ck_{tablename}_{column_name} CHECK "
        f"({column_name} IN ({', '.join(repr(member.value) for member in enum_cls)}))"
    ) in ddl

    checks = [
        constraint
        for constraint in table_of(tablename).constraints
        if isinstance(constraint, CheckConstraint)
        and list(constraint.columns.keys()) == [column_name]
    ]
    assert len(checks) == 1
    assert checks[0].name == f"ck_{tablename}_{column_name}"


def test_no_native_postgresql_enum_columns() -> None:
    """Ни одной нативной PostgreSQL ENUM-колонки."""

    for tablename in Base.metadata.tables:
        for col in table_of(tablename).c:
            assert not isinstance(col.type, PostgresEnum)


def table_ddl(tablename: str) -> str:
    """Компилирует CREATE TABLE диалектом PostgreSQL."""

    return str(CreateTable(table_of(tablename)).compile(dialect=postgresql.dialect()))


def test_explicit_check_constraints_from_doc() -> None:
    """CHECK-ограничения ровно из docs/04."""

    grade_ddl = table_ddl("grade_scales")
    assert "CHECK (primary_score >= 0)" in grade_ddl

    profile_ddl = table_ddl("student_profiles")
    assert "CHECK (lesson_price >= 0)" in profile_ddl


def test_auth_tokens_covered_index() -> None:
    """Индекс (user_id, purpose) — требование docs/04 §2.5."""

    indexes = {
        (index.name, frozenset(column.name for column in index.columns))
        for index in table_of("auth_tokens").indexes
    }
    assert ("ix_auth_tokens_user_id_purpose", frozenset({"user_id", "purpose"})) in indexes


@pytest.mark.parametrize(
    ("tablename", "column_name", "target", "ondelete"),
    FOREIGN_KEYS,
    ids=[f"{table_name}.{colname}" for table_name, colname, _, _ in FOREIGN_KEYS],
)
def test_foreign_keys_target_and_on_delete(
    tablename: str, column_name: str, target: str, ondelete: str
) -> None:
    """FK: цель и действие ON DELETE совпадают с docs/04."""

    (fk,) = col_of(tablename, column_name).foreign_keys
    assert fk.target_fullname == target
    assert fk.ondelete == ondelete


def test_relationships_lazy_raise_and_back_populates() -> None:
    """Связи: lazy="raise" и согласованный back_populates."""

    configure_mappers()
    for model in ALL_MODELS:
        for rel in model.__mapper__.relationships:
            assert rel.lazy == "raise", f"{model.__name__}.{rel.key}"
            if rel.back_populates is not None:
                reverse = rel.mapper.class_.__mapper__.relationships[rel.back_populates]
                assert reverse.back_populates == rel.key


def test_models_import_from_src_db_on_this_python() -> None:
    """Модели реально импортируются из пакета src.db."""

    db = importlib.import_module("src.db")
    for name in (
        "Subject",
        "ExamType",
        "GradeScale",
        "User",
        "StudentProfile",
        "StudentSubject",
        "Guardian",
        "AuthToken",
        "AuditLog",
        "Base",
        "TimestampMixin",
        "enum_varchar",
    ):
        assert hasattr(db, name)

    models = importlib.import_module("src.db.models")
    assert models.Subject.__tablename__ == "subjects"
    assert models.AuditLog.__tablename__ == "audit_log"
