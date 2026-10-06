"""Интеграционные тесты миграции и сидов T1.03 (PostgreSQL 16, Testcontainers).

Проверяют на реальной БД (образ postgres:16 из tests/conftest.py):

- ``alembic upgrade head`` на пустой базе создаёт все 9 таблиц T1.02
  и расширение ``btree_gist``;
- идемпотентность ``scripts/seed_reference.py``: повторный запуск не создаёт
  дублей, количества строк шкал равны 30/33/22/32 (docs/04 §10);
- ``alembic downgrade base`` полностью удаляет созданное (рабочий откат);
- повторный ``alembic upgrade head`` после отката проходит без ошибок.

Если Docker-демон недоступен, тесты корректно пропускаются (в проекте уже
есть обязательная зависимость docker для testcontainers) — это НЕ ослабляет
проверки на машине разработчика, где Docker запущен.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from alembic import command as alembic_command
from alembic.config import Config

# Импорт сида живёт в scripts/ — проверяем его напрямую (идемпотентность).
from scripts.seed_reference import seed
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

# Корень репозитория: alembic.ini лежит здесь (ADR 0002).
ROOT = Path(__file__).resolve().parents[2]

# Тестовая база: отдельная от lms_test, чтобы не мешать другим тестам.
MIGRATION_DB = "lms_t103_migration"

# Ожидаемое количество строк шкал 2026 по коду экзамена (постановка T1.03).
EXPECTED_SCALE_ROWS = {
    "ege_informatics": 30,  # первичные 0–29
    "ege_math_profile": 33,  # первичные 0–32
    "oge_informatics": 22,  # первичные 0–21
    "oge_math": 32,  # первичные 0–31
}

# Все 9 таблиц этапа T1.02 (docs/04 §1–§8).
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


def _docker_available() -> bool:
    """Есть ли доступный Docker-демон (тесты умеют работать с ним и без него)."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:  # noqa: BLE001 - любой сбой клиента = Docker недоступен
        return False


docker_required = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker недоступен в текущем окружении — интеграционные тесты пропущены",
)


def _container_admin_url(postgres_container: PostgresContainer) -> str:
    """PSQL-DSN (asyncpg-совместимый) к базe администратора контейнера."""
    host = postgres_container.get_container_host_ip()
    port = int(postgres_container.get_exposed_port(5432))
    return f"postgresql://test:test@{host}:{port}/lms_test"


def _migration_dsn(postgres_container: PostgresContainer) -> tuple[str, str]:
    """Строки подключения к чистой тестовой базе.

    Returns:
        Пар ``(sync_url, async_url)``: первый — для Alembic (psycopg3 через
        префикс ``postgresql+asyncpg``), второй — для проверок (asyncpg).
    """
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
        password="test",  # noqa: S106
        database=MIGRATION_DB,
        host=host,
        port=port,
    ).render_as_string(hide_password=False)
    return sync_url, async_url


# Модуль пропускается целиком, если Docker недоступен (см. _docker_available).
pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker недоступен в текущем окружении — интеграционные тесты пропущены",
)


@pytest.fixture(scope="module")
def clean_migration_database(
    postgres_container: PostgresContainer,
) -> Iterator[str]:
    """Пересоздаёт пустую базу ``lms_t103_migration`` для всего модуля."""
    admin_dsn = _container_admin_url(postgres_container)

    async def _recreate() -> None:
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(f"DROP DATABASE IF EXISTS {MIGRATION_DB} WITH (FORCE)")
            await conn.execute(f"CREATE DATABASE {MIGRATION_DB}")
        finally:
            await conn.close()

    # Отдельный цикл: фикстура синхронная, а asyncpg требует event loop.
    asyncio.run(_recreate())
    yield MIGRATION_DB
    asyncio.run(_recreate())


def _run_alembic(sync_url: str, action: str) -> None:
    """Выполнить команду Alembic против тестовой базы.

    env.py берёт DATABASE_URL из Settings (переменная окружения) — подменяем
    её на адрес тестовой базы на время команды и возвращаем обратно.

    run_migrations_online() в env.py сама поднимает цикл через asyncio.run(),
    что запрещено, если цикл уже запущен — поэтому команда выполняется в
    отдельном потоке (там цикла нет, как в CLI).
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
            else:  # pragma: no cover - защита от опечатки в тестах
                raise ValueError(action)
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_command).result()


def _run_in_fresh_loop(coro_factory: Any) -> None:
    """Выполняет корутину в НОВОМ событийном цикле.

    pytest-asyncio работает в режиме auto: синхронные тесты могут исполняться
    внутри уже запущенного цикла, где прямой asyncio.run() запрещён. Поэтому
    если цикл уже есть — корутина выполняется в отдельном потоке, где цикла
    нет и asyncio.run() разрешён.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro_factory())
    else:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(coro_factory())).result()


async def _table_names(engine: AsyncEngine) -> set[str]:
    """Имена публичных таблиц схемы public текущей базы."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
        ).fetchall()
    return {str(r[0]) for r in rows}


async def _extensions(engine: AsyncEngine) -> set[str]:
    """Установленные расширения БД."""
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT extname FROM pg_extension"))).fetchall()
    return {str(r[0]) for r in rows}


async def _scale_counts(engine: AsyncEngine) -> dict[str, int]:
    """Количество строк шкал по коду типа экзамена."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT et.code, count(*)::int"
                    " FROM grade_scales gs"
                    " JOIN exam_types et ON et.id = gs.exam_type_id"
                    " GROUP BY et.code"
                )
            )
        ).fetchall()
    return {str(code): int(cnt) for code, cnt in rows}


async def _row_count(engine: AsyncEngine, table: str) -> int:
    """Число строк в таблице (имя передаётся только из констант этого теста)."""
    assert table in T102_TABLES | {"alembic_version"}
    query = "SELECT count(*) FROM " + table  # noqa: S608 - имя из белого списка выше
    async with engine.connect() as conn:
        value = await conn.scalar(text(query))
    return int(value)


@docker_required
def test_full_migration_cycle_and_seeds(
    clean_migration_database: str,
    postgres_container: PostgresContainer,
) -> None:
    """Сквозной цикл: пустая БД → upgrade head → сид ×2 → downgrade → upgrade.

    Один тест фиксирует строгий порядок шагов, как в проверке T1.03/T1.04.
    """
    del clean_migration_database  # факт существования чистой базы держит фикстура
    sync_url, async_url = _migration_dsn(postgres_container)
    engine = create_async_engine(async_url, poolclass=NullPool)

    async def scenario() -> None:
        # 1) upgrade head на ПУСТОЙ базе: 9 таблиц T1.02 + alembic_version.
        _run_alembic(sync_url, "upgrade_head")
        tables = await _table_names(engine)
        assert tables == T102_TABLES | {"alembic_version"}, f"нашли: {tables}"

        # Расширение btree_gist создано первой миграцией (docs/04 §0).
        assert "btree_gist" in await _extensions(engine)

        # 2) Первый прогон сида заполняет справочники.
        first = await seed(async_url)
        assert first["subjects"] == 2
        assert first["exam_types"] == 4
        assert first["grade_scales"] == sum(EXPECTED_SCALE_ROWS.values())

        # Полнота шкал на живой БД: 30/33/22/32 (docs/04 §10).
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS

        # 3) Идемпотентность: повторный запуск не создаёт дублей.
        second = await seed(async_url)
        assert second == {"subjects": 0, "exam_types": 0, "grade_scales": 0}
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS
        assert await _row_count(engine, "subjects") == 2
        assert await _row_count(engine, "exam_types") == 4

        # 4) downgrade base полностью удаляет созданное (рабочий откат).
        # Служебная таблица alembic_version сохраняется Alembic и при откате,
        # важно: НЕ осталось ни одной таблицы предметной области.
        _run_alembic(sync_url, "downgrade_base")
        after_downgrade = await _table_names(engine)
        assert after_downgrade <= {"alembic_version"}, (
            f"после отката остались: {after_downgrade}"
        )

        # 5) Повторный upgrade head после отката проходит без ошибок.
        _run_alembic(sync_url, "upgrade_head")
        after_reupgrade = await _table_names(engine)
        assert after_reupgrade == T102_TABLES | {"alembic_version"}
        assert "btree_gist" in await _extensions(engine)

    try:
        _run_in_fresh_loop(scenario)
    finally:
        _run_in_fresh_loop(engine.dispose)
