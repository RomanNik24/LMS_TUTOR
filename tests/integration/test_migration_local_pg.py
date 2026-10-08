"""Интеграционные тесты миграции и сидов T1.03 на локальном PostgreSQL.

Переменная ``TEST_DATABASE_URL`` задаёт asyncpg-DSN к базе, в которой
тесту разрешено пересоздавать public schema.

Проверяется полный цикл T1.03:

- upgrade head на пустой базе;
- точный набор таблиц T1.02;
- btree_gist;
- отсутствие native PostgreSQL ENUM;
- CHECK/FK/UNIQUE/index constraints;
- idempotent seed;
- полнота шкал 30/33/22/32;
- Alembic drift check;
- downgrade и удаление btree_gist;
- повторный upgrade.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict
from urllib.parse import unquote, urlsplit

import asyncpg
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.seed_reference import seed  # noqa: E402 - импорт после sys.path.insert

EXPECTED_SCALE_ROWS = {
    "ege_informatics": 30,
    "ege_math_profile": 33,
    "oge_informatics": 22,
    "oge_math": 32,
}

T102_TABLES = {
    "subjects",
    "users",
    "exam_types",
    "student_profiles",
    "guardians",
    "student_subjects",
    "auth_tokens",
    "audit_log",
    "grade_scales",
    "schedule_templates",
    "schedule_template_participants",
    "lessons",
    "lesson_participants",
    "homeworks",
    "homework_materials",
    "homework_assignments",
    "homework_extensions",
    "homework_files",
    "notifications",
    "mock_exam_results",
    "catalog_items",
}

EXPECTED_FK_DELETE_RULES = {
    "fk_audit_log_actor_user_id": "n",
    "fk_auth_tokens_created_by": "n",
    "fk_auth_tokens_user_id": "c",
    "fk_exam_types_subject_id": "r",
    "fk_grade_scales_exam_type_id": "c",
    "fk_guardians_linked_user_id_fk": "n",
    "fk_guardians_student_id_fk": "c",
    "fk_student_profiles_student_id": "c",
    "fk_student_profiles_teacher_id": "r",
    "fk_student_subjects_subject_id": "c",
    "fk_student_subjects_student_id": "c",
    "fk_schedule_templates_teacher_id": "r",
    "fk_schedule_templates_subject_id": "r",
    "fk_schedule_template_participants_template_id": "c",
    "fk_schedule_template_participants_student_id": "r",
    "fk_lessons_teacher_id": "r",
    "fk_lessons_subject_id": "r",
    "fk_lessons_template_id": "n",
    "fk_lessons_cancelled_by": "n",
    "fk_lesson_participants_lesson_id": "c",
    "fk_lesson_participants_student_id": "r",
    "fk_homeworks_created_by": "r",
    "fk_homeworks_lesson_id": "n",
    "fk_homeworks_subject_id": "r",
    "fk_homeworks_exam_type_id": "r",
    "fk_homework_materials_homework_id": "c",
    "fk_homework_assignments_homework_id": "c",
    "fk_homework_assignments_student_id": "r",
    "fk_homework_assignments_graded_by": "n",
    "fk_homework_extensions_assignment_id": "c",
    "fk_homework_extensions_created_by": "r",
    "fk_homework_files_assignment_id": "c",
    "fk_homework_files_uploaded_by": "r",
    "fk_notifications_user_id": "c",
    "fk_mock_exam_results_student_id": "r",
    "fk_mock_exam_results_exam_type_id": "r",
    "fk_mock_exam_results_assignment_id": "n",
    "fk_mock_exam_results_created_by": "r",
}

EXPECTED_CHECK_NAMES = {
    "ck_users_role",
    "ck_exam_types_kind",
    "ck_exam_types_result_kind",
    "ck_auth_tokens_purpose",
    "ck_grade_scales_primary_score_nonneg",
    "ck_student_profiles_lesson_price_nonneg",
    "ck_schedule_templates_weekday_range",
    "ck_schedule_templates_duration_positive",
    "ck_lessons_status",
    "ck_lessons_end_after_start",
    "ck_lesson_participants_attendance",
    "ck_lesson_participants_price_snapshot_nonneg",
    "ck_homeworks_kind",
    "ck_homeworks_due_mode",
    "ck_homeworks_max_score_positive",
    "ck_homeworks_mock_exam_needs_exam_type",
    "ck_homework_assignments_status",
    "ck_homework_assignments_submission_type",
    "ck_homework_assignments_extensions_count_range",
    "ck_homework_assignments_score_nonneg",
    "ck_homework_files_role",
    "ck_notifications_status",
    "ck_mock_exam_results_primary_score_non_negative",
}


class AsyncpgConnectKwargs(TypedDict):
    """Параметры подключения asyncpg."""

    host: str
    port: int
    user: str | None
    password: str | None
    database: str


def _table_names_query() -> str:
    return "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"


async def _table_names(engine: AsyncEngine) -> set[str]:
    """Имена публичных таблиц."""

    async with engine.connect() as conn:
        rows = (await conn.execute(text(_table_names_query()))).fetchall()
    return {str(row[0]) for row in rows}


async def _extensions(engine: AsyncEngine) -> set[str]:
    """Установленные PostgreSQL extensions."""

    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT extname FROM pg_extension"))).fetchall()
    return {str(row[0]) for row in rows}


async def _scale_counts(engine: AsyncEngine) -> dict[str, int]:
    """Количество строк grade_scales по коду экзамена."""

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT et.code, count(*)::int "
                    "FROM grade_scales gs "
                    "JOIN exam_types et ON et.id = gs.exam_type_id "
                    "GROUP BY et.code"
                )
            )
        ).fetchall()
    return {str(code): int(count) for code, count in rows}


async def _row_count(engine: AsyncEngine, table: str) -> int:
    """Число строк в белом списке таблиц T1.03."""

    assert table in T102_TABLES | {"alembic_version"}
    query = "SELECT count(*) FROM " + table  # noqa: S608 - имя таблицы из белого списка T102_TABLES
    async with engine.connect() as conn:
        value = await conn.scalar(text(query))
    return int(value)


async def _constraint_definitions(engine: AsyncEngine) -> dict[str, str]:
    """Вернуть определения CHECK-ограничений public-схемы."""

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) "
                    "FROM pg_constraint "
                    "WHERE contype = 'c' "
                    "AND connamespace = 'public'::regnamespace "
                    "ORDER BY conname"
                )
            )
        ).fetchall()
    return {str(name): str(definition) for name, definition in rows}


async def _native_enum_count(engine: AsyncEngine) -> int:
    """Число PostgreSQL native ENUM type объектов."""

    async with engine.connect() as conn:
        value = await conn.scalar(text("SELECT count(*) FROM pg_type WHERE typtype = 'e'"))
    return int(value)


def _parse_dsn(dsn: str) -> AsyncpgConnectKwargs:
    """Разобрать DSN в параметры asyncpg."""

    normalized = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    parts = urlsplit(normalized)

    return {
        "host": parts.hostname or "localhost",
        "port": parts.port or 5432,
        "user": unquote(parts.username) if parts.username else None,
        "password": unquote(parts.password) if parts.password else None,
        "database": parts.path.lstrip("/") or "postgres",
    }


def _run_in_fresh_loop(coro_factory: Callable[[], Awaitable[None]]) -> None:
    """Выполнить coroutine factory в свежем asyncio loop."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro_factory())
    else:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(coro_factory())).result()


def _run_in_fresh_loop_probe(coro_factory: Callable[[], Awaitable[bool]]) -> bool:
    """Выполнить bool-coroutine в свежем asyncio loop."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    else:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return bool(pool.submit(lambda: asyncio.run(coro_factory())).result())


def _get_test_dsn() -> str:
    """Получить TEST_DATABASE_URL или пропустить локальный цикл."""

    dsn = os.environ.get("TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL не задан — локальный PostgreSQL-цикл пропущен")

    async def _probe() -> bool:
        try:
            conn = await asyncpg.connect(**_parse_dsn(dsn))
            await conn.close()
            return True
        except Exception:  # noqa: BLE001 - недоступность БД означает skip
            return False

    if not _run_in_fresh_loop_probe(_probe):
        pytest.skip("PostgreSQL по TEST_DATABASE_URL недоступен — локальный цикл пропущен")

    return dsn


@pytest.fixture(scope="module")
def local_test_dsn() -> str:
    """DSN локальной тестовой базы."""

    return _get_test_dsn()


async def _clean_schema_async(dsn: str) -> None:
    """Пересоздать public schema целевой тестовой базы."""

    conn = await asyncpg.connect(**_parse_dsn(dsn))
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


@pytest.fixture()
def clean_local_schema(local_test_dsn: str) -> Iterator[None]:
    """Гарантировать чистую public schema до и после теста."""

    _run_in_fresh_loop(lambda: _clean_schema_async(local_test_dsn))
    try:
        yield
    finally:
        _run_in_fresh_loop(lambda: _clean_schema_async(local_test_dsn))


def _run_alembic_local(dsn: str, action: str) -> None:
    """Выполнить Alembic в отдельном потоке."""

    def _command() -> None:
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = dsn

        try:
            cfg = Config(os.path.join(ROOT, "alembic.ini"))
            cfg.set_main_option(
                "script_location",
                os.path.join(ROOT, "src", "db", "migrations"),
            )

            if action == "upgrade_head":
                alembic_command.upgrade(cfg, "head")
            elif action == "downgrade_base":
                alembic_command.downgrade(cfg, "base")
            elif action == "check":
                alembic_command.check(cfg)
            else:  # pragma: no cover - защита от ошибки в самом тесте
                raise ValueError(action)
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_command).result()


def test_upgrade_seed_idempotent_downgrade_reupgrade_local(
    clean_local_schema: None,
    local_test_dsn: str,
) -> None:
    """Полный T1.03 цикл на локальном PostgreSQL."""

    del clean_local_schema

    engine: AsyncEngine = create_async_engine(local_test_dsn, poolclass=NullPool)

    async def scenario() -> None:
        _run_alembic_local(local_test_dsn, "upgrade_head")

        tables = await _table_names(engine)
        assert tables == T102_TABLES | {"alembic_version"}
        assert "btree_gist" in await _extensions(engine)
        assert await _native_enum_count(engine) == 0

        checks = await _constraint_definitions(engine)
        assert set(checks) == EXPECTED_CHECK_NAMES
        assert "owner" in checks["ck_users_role"]
        assert "manager" in checks["ck_users_role"]
        assert "student" in checks["ck_users_role"]
        assert "oge" in checks["ck_exam_types_kind"]
        assert "ege" in checks["ck_exam_types_kind"]
        assert "grade_2_5" in checks["ck_exam_types_result_kind"]
        assert "test_100" in checks["ck_exam_types_result_kind"]
        assert "invite" in checks["ck_auth_tokens_purpose"]
        assert "web_login" in checks["ck_auth_tokens_purpose"]

        _run_alembic_local(local_test_dsn, "check")

        first = await seed(local_test_dsn)
        assert first["subjects"] == 2
        assert first["exam_types"] == 4
        assert first["grade_scales"] == sum(EXPECTED_SCALE_ROWS.values())
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS

        second = await seed(local_test_dsn)
        assert second == {"subjects": 0, "exam_types": 0, "grade_scales": 0}
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS
        assert await _row_count(engine, "subjects") == 2
        assert await _row_count(engine, "exam_types") == 4
        assert await _row_count(engine, "grade_scales") == sum(EXPECTED_SCALE_ROWS.values())

        _run_alembic_local(local_test_dsn, "downgrade_base")

        assert await _table_names(engine) == {"alembic_version"}
        assert "btree_gist" not in await _extensions(engine)

        _run_alembic_local(local_test_dsn, "upgrade_head")

        assert await _table_names(engine) == T102_TABLES | {"alembic_version"}
        assert "btree_gist" in await _extensions(engine)
        assert await _native_enum_count(engine) == 0

        _run_alembic_local(local_test_dsn, "check")

    try:
        _run_in_fresh_loop(scenario)
    finally:
        _run_in_fresh_loop(engine.dispose)


def test_constraints_created_by_migration_local(
    clean_local_schema: None,
    local_test_dsn: str,
) -> None:
    """Проверить PK/FK/UNIQUE/CHECK/index constraints на живой PostgreSQL."""

    del clean_local_schema

    _run_alembic_local(local_test_dsn, "upgrade_head")
    engine: AsyncEngine = create_async_engine(local_test_dsn, poolclass=NullPool)

    async def check() -> None:
        async with engine.connect() as conn:
            enums = await conn.scalar(text("SELECT count(*) FROM pg_type WHERE typtype = 'e'"))
            assert int(enums) == 0

            fk_rows = (
                await conn.execute(
                    text(
                        "SELECT conname, confdeltype::text "
                        "FROM pg_constraint "
                        "WHERE contype = 'f' AND connamespace = 'public'::regnamespace "
                        "ORDER BY conname"
                    )
                )
            ).fetchall()
            confdel = {str(name): str(delete_type) for name, delete_type in fk_rows}
            assert confdel == EXPECTED_FK_DELETE_RULES

            checks = await _constraint_definitions(engine)
            assert set(checks) == EXPECTED_CHECK_NAMES

            unique_rows = (
                await conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE contype = 'u' AND connamespace = 'public'::regnamespace "
                        "ORDER BY conname"
                    )
                )
            ).fetchall()
            unique_names = {str(row[0]) for row in unique_rows}
            assert unique_names == {
                "uq_subjects_code",
                "uq_exam_types_code",
                "uq_users_telegram_id",
                "uq_auth_tokens_token_hash",
                "uq_lessons_template_id_start_at",
                "uq_homework_assignments_homework_id_student_id",
                "uq_notifications_dedup_key",
                "uq_mock_exam_results_assignment_id",
                "uq_grade_scales_exam_type_id_valid_year_primary_score",
            }

            index_rows = (
                await conn.execute(
                    text(
                        "SELECT indexname "
                        "FROM pg_indexes "
                        "WHERE schemaname = 'public' "
                        "AND tablename = 'auth_tokens'"
                    )
                )
            ).fetchall()
            assert {str(row[0]) for row in index_rows} >= {"ix_auth_tokens_user_id_purpose"}

    try:
        _run_in_fresh_loop(check)
    finally:
        _run_in_fresh_loop(engine.dispose)
