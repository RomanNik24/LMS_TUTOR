"""Интеграционные тесты миграции и сидов T1.03 (PostgreSQL 16, Testcontainers).

Проверяют на реальной PostgreSQL:

- alembic upgrade head на пустой базе;
- точный набор девяти таблиц T1.02;
- btree_gist;
- отсутствие PostgreSQL native ENUM;
- точные enum CHECK-ограничения;
- idempotency reference seed;
- полноту четырёх шкал 2026;
- alembic check без drift;
- рабочий downgrade;
- удаление созданного btree_gist при downgrade;
- повторный upgrade head.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asyncpg
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from scripts.seed_reference import seed
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[2]

MIGRATION_DB = "lms_t103_migration"

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
}

EXPECTED_CHECK_NAMES = {
    "ck_users_role",
    "ck_exam_types_kind",
    "ck_exam_types_result_kind",
    "ck_auth_tokens_purpose",
    "ck_grade_scales_primary_score_nonneg",
    "ck_student_profiles_lesson_price_nonneg",
}


def _docker_available() -> bool:
    """Есть ли доступный Docker-демон."""

    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.close()
        return True
    except Exception:  # noqa: BLE001 - недоступность Docker обрабатывается skip
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker недоступен в текущем окружении — интеграционные тесты пропущены",
)


def _container_admin_url(postgres_container: PostgresContainer) -> str:
    """DSN к административной базе контейнера."""

    host = postgres_container.get_container_host_ip()
    port = int(postgres_container.get_exposed_port(5432))
    return f"postgresql://test:test@{host}:{port}/lms_test"


def _migration_dsn(postgres_container: PostgresContainer) -> tuple[str, str]:
    """Строки подключения к тестовой базе."""

    host = postgres_container.get_container_host_ip()
    port = int(postgres_container.get_exposed_port(5432))

    sync_url = URL.create(
        "postgresql+asyncpg",
        username="test",
        password="test",  # noqa: S106 - тестовые креды контейнера
        database=MIGRATION_DB,
        host=host,
        port=port,
    ).render_as_string(hide_password=False)

    async_url = URL.create(
        "postgresql+asyncpg",
        username="test",
        password="test",  # noqa: S106 - тестовые креды контейнера
        database=MIGRATION_DB,
        host=host,
        port=port,
    ).render_as_string(hide_password=False)

    return sync_url, async_url


@pytest.fixture(scope="module")
def clean_migration_database(
    postgres_container: PostgresContainer,
) -> Iterator[str]:
    """Пересоздаёт пустую базу T1.03 для модуля."""

    admin_dsn = _container_admin_url(postgres_container)

    async def _recreate() -> None:
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(f"DROP DATABASE IF EXISTS {MIGRATION_DB} WITH (FORCE)")
            await conn.execute(f"CREATE DATABASE {MIGRATION_DB}")
        finally:
            await conn.close()

    asyncio.run(_recreate())
    yield MIGRATION_DB
    asyncio.run(_recreate())


def _run_alembic(sync_url: str, action: str) -> None:
    """Выполнить команду Alembic в отдельном потоке.

    Отдельный поток обязателен для синхронного Alembic API, потому что
    ``env.py`` запускает async migration loop через ``asyncio.run()``.
    """

    def _command() -> None:
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = sync_url
        try:
            cfg = Config(str(ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(ROOT / "src/db/migrations"))

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


def _run_in_fresh_loop(coro_factory: Callable[[], Awaitable[None]]) -> None:
    """Выполнить coroutine factory в свежем asyncio loop."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro_factory())
    else:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(coro_factory())).result()


async def _table_names(engine: AsyncEngine) -> set[str]:
    """Имена публичных таблиц."""

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
        ).fetchall()
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


def test_full_migration_cycle_and_seeds(
    clean_migration_database: str,
    postgres_container: PostgresContainer,
) -> None:
    """Полный T1.03 цикл: upgrade → check → seed ×2 → downgrade → upgrade."""

    del clean_migration_database

    sync_url, async_url = _migration_dsn(postgres_container)
    engine = create_async_engine(async_url, poolclass=NullPool)

    async def scenario() -> None:
        _run_alembic(sync_url, "upgrade_head")

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

        # Alembic autogenerate должен видеть чистую схему без drift.
        _run_alembic(sync_url, "check")

        first = await seed(async_url)
        assert first["subjects"] == 2
        assert first["exam_types"] == 4
        assert first["grade_scales"] == sum(EXPECTED_SCALE_ROWS.values())
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS

        second = await seed(async_url)
        assert second == {"subjects": 0, "exam_types": 0, "grade_scales": 0}
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS
        assert await _row_count(engine, "subjects") == 2
        assert await _row_count(engine, "exam_types") == 4
        assert await _row_count(engine, "grade_scales") == sum(EXPECTED_SCALE_ROWS.values())

        _run_alembic(sync_url, "downgrade_base")

        after_downgrade = await _table_names(engine)
        assert after_downgrade == {"alembic_version"}
        assert "btree_gist" not in await _extensions(engine)

        _run_alembic(sync_url, "upgrade_head")

        after_reupgrade = await _table_names(engine)
        assert after_reupgrade == T102_TABLES | {"alembic_version"}
        assert "btree_gist" in await _extensions(engine)
        assert await _native_enum_count(engine) == 0

        _run_alembic(sync_url, "check")

    try:
        _run_in_fresh_loop(scenario)
    finally:
        _run_in_fresh_loop(engine.dispose)
