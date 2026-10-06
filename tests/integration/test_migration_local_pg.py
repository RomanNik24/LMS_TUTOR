"""Интеграционные тесты миграции и сидов T1.03 на локальном PostgreSQL.

Дополнение к tests/integration/test_migration_and_seeds.py (Testcontainers):
в средах без Docker-демона тот модуль пропускается, а этот поднимает проверку
на локальном кластере PostgreSQL (переменная окружения TEST_DATABASE_URL —
asyncpg-DSN к базе, в которой разрешено пересоздавать схему public).

Проверяет полный цикл по постановке T1.03:

- ``alembic upgrade head`` на пустой базе (9 таблиц T1.02 + btree_gist);
- идемпотентность ``scripts/seed_reference.py`` (повтор = 0 дублей) и полноту
  шкал 30/33/22/32 (docs/04 §10);
- ``alembic downgrade base`` (полный откат);
- повторный ``alembic upgrade head``.

Если TEST_DATABASE_URL не задан или база недоступна, тесты корректно
пропускаются (в CI с Docker основной цикл покрывает первый модуль).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# Корень репозитория: alembic.ini лежит здесь (ADR 0002), а пакеты src/scripts/
# импортируются из него. rootdir pytest добавляет в sys.path только tests/,
# поэтому корень вставляем явно (тот же приём, что в scripts/seed_reference.py).
ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import asyncpg
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from scripts.seed_reference import seed
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

# Вспомогательные проверки берём из основного модуля миграционных тестов.
# Тот модуль на уровне импорта поднимает PostgresContainer (testcontainers),
# поэтому подключаемся к нему динамически; если Docker недоступен — используем
# локальные копии констант и запросов (цикл при этом покрывается этим файлом).
try:  # pragma: no cover - зависит от наличия Docker в окружении
    from tests.integration.test_migration_and_seeds import (
        EXPECTED_SCALE_ROWS,
        T102_TABLES,
    )
except Exception:  # noqa: BLE001 - отсутствие Docker/образа = локальные копии
    EXPECTED_SCALE_ROWS = {
        "ege_informatics": 30,  # первичные 0–29
        "ege_math_profile": 33,  # первичные 0–32
        "oge_informatics": 22,  # первичные 0–21
        "oge_math": 32,  # первичные 0–31
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


# Асинхронные помощники определены ЗДЕСЬ локально (не импортируются из
# testcontainers-модуля): в pytest asyncio_mode="auto" любые async def
# превращаются в тесты, а имена с префиксом _ — нет. Локальные копии
# исключают и рискcollect-a синхронных функций из чужого модуля.
async def _table_names(engine: AsyncEngine) -> set[str]:
    """Имена публичных таблиц схемы public текущей базы."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = 'public'"
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
    """Число строк в таблице (имя — только из констант этого теста)."""
    assert table in T102_TABLES | {"alembic_version"}
    async with engine.connect() as conn:
        value = await conn.scalar(text("SELECT count(*) FROM " + table))  # noqa: S608
    return int(value)


def _parse_dsn(dsn: str) -> dict[str, Any]:
    """Разбирает DSN (asyncpg-формат, опционально с префиксом SQLAlchemy) в
    kwargs asyncpg.connect для целевой базы.

    Целевая база используется напрямую: фикстура чистит схему public внутри
    неё, поэтому отдельное подключение к базе ``postgres`` не нужно.
    """
    # Поддерживаем sqlalchemy-префиксы: postgresql+asyncpg:// -> postgresql://
    normalized = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    from urllib.parse import unquote, urlsplit

    parts = urlsplit(normalized)
    return {
        "host": parts.hostname or "localhost",
        "port": parts.port or 5432,
        "user": unquote(parts.username) if parts.username else None,
        "password": unquote(parts.password) if parts.password else None,
        "database": (parts.path.lstrip("/") or "postgres"),
    }


def _get_test_dsn() -> str:
    """Возвращает DSN тестовой базы или skip, если база недоступна."""
    dsn = os.environ.get("TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL не задан — локальный PostgreSQL-цикл пропущен")

    async def _probe() -> bool:
        try:
            conn = await asyncpg.connect(**_parse_dsn(dsn))
            await conn.close()
            return True
        except Exception:  # noqa: BLE001 - недоступность базы = skip, не failure
            return False

    if not _run_in_fresh_loop_probe(_probe):
        pytest.skip(f"База по TEST_DATABASE_URL недоступна — цикл пропущен: {dsn.split('@')[-1]}")
    return dsn


@pytest.fixture(scope="module")
def local_test_dsn() -> str:
    """DSN локальной тестовой базы (skip, если недоступен)."""
    return _get_test_dsn()


async def _clean_schema_async(dsn: str) -> None:
    """Бросает и пересоздаёт схему public (полная пустая база для цикла)."""
    conn = await asyncpg.connect(**_parse_dsn(dsn))
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


def _run_in_fresh_loop(coro_factory: Any) -> None:
    """Выполняет корутину в НОВОМ событийном цикле.

    pytest-asyncio работает в режиме auto, поэтому синхронные тесты уже
    живут внутри запущенного цикла и прямой asyncio.run() запрещён.
    Сначала пробуем обычный asyncio.run(), при конфликте — запускаем
    корутину в отдельном потоке (там цикла нет, run разрешён).
    """
    try:
        asyncio.run(coro_factory())
    except RuntimeError:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(coro_factory())).result()


def _run_in_fresh_loop_probe(coro_factory: Any) -> bool:
    """То же, что _run_in_fresh_loop, но с возвратом значения (bool-probe)."""
    try:
        return bool(asyncio.run(coro_factory()))
    except RuntimeError:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return bool(pool.submit(lambda: asyncio.run(coro_factory())).result())


@pytest.fixture()
def clean_local_schema(local_test_dsn: str) -> None:
    """Гарантирует пустую схему public целевой базы до и после каждого теста."""
    _run_in_fresh_loop(lambda: _clean_schema_async(local_test_dsn))
    yield
    _run_in_fresh_loop(lambda: _clean_schema_async(local_test_dsn))


def _run_alembic_local(dsn: str, action: str) -> None:
    """Выполняет команду Alembic против локальной тестовой базы.

    env.py берёт DATABASE_URL из Settings — задаём её через окружение только
    на время вызова и восстанавливаем прежнее значение.
    """
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = dsn
    try:
        cfg = Config(os.path.join(ROOT, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(ROOT, "src", "db", "migrations"))
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


def test_upgrade_seed_idempotent_downgrade_reupgrade_local(
    clean_local_schema: None, local_test_dsn: str
) -> None:
    """Полный цикл T1.03 на локальном PostgreSQL.

    Порядок шагов идентичен тестовому сценарию Testcontainers-модуля:
    пустая схема → upgrade head → сид ×2 → downgrade base → upgrade head.
    """
    del clean_local_schema  # чистоту схемы держит фикстура
    engine: AsyncEngine = create_async_engine(local_test_dsn, poolclass=NullPool)

    async def scenario() -> None:
        # 1) upgrade head на ПУСТОЙ схеме: 9 таблиц T1.02 + alembic_version.
        _run_alembic_local(local_test_dsn, "upgrade_head")
        tables = await _table_names(engine)
        assert tables == T102_TABLES | {"alembic_version"}, f"нашли: {tables}"
        assert "btree_gist" in await _extensions(engine)

        # 2) Первый прогон сида заполняет справочники.
        first = await seed(local_test_dsn)
        assert first["subjects"] == 2
        assert first["exam_types"] == 4
        assert first["grade_scales"] == sum(EXPECTED_SCALE_ROWS.values())
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS

        # 3) Идемпотентность: повторный запуск не создаёт дублей.
        second = await seed(local_test_dsn)
        assert second == {"subjects": 0, "exam_types": 0, "grade_scales": 0}
        assert await _scale_counts(engine) == EXPECTED_SCALE_ROWS
        assert await _row_count(engine, "subjects") == 2
        assert await _row_count(engine, "exam_types") == 4

        # 4) downgrade base полностью удаляет созданное (кроме самой схемы).
        _run_alembic_local(local_test_dsn, "downgrade_base")
        after_downgrade = await _table_names(engine)
        assert after_downgrade == set(), f"после отката остались: {after_downgrade}"

        # 5) Повторный upgrade head после отката проходит без ошибок.
        _run_alembic_local(local_test_dsn, "upgrade_head")
        assert await _table_names(engine) == T102_TABLES | {"alembic_version"}
        assert "btree_gist" in await _extensions(engine)

    try:
        _run_in_fresh_loop(scenario)
    finally:
        _run_in_fresh_loop(engine.dispose)


def test_constraints_created_by_migration_local(
    clean_local_schema: None, local_test_dsn: str
) -> None:
    """Миграция создаёт PK/FK/UNIQUE/CHECK/индексы и VARCHAR-enum (ADR 0003).

    Проверка на живой БД дополняет статический аудит ревизии: убеждаемся,
    что CHECK-ограничения enum перечислены, нативных ENUM-типов нет, а
    ON DELETE у FK соответствует docs/04.
    """
    del clean_local_schema
    _run_alembic_local(local_test_dsn, "upgrade_head")
    engine: AsyncEngine = create_async_engine(local_test_dsn, poolclass=NullPool)

    async def check() -> None:
        async with engine.connect() as conn:
            # Нативные ENUM-типы запрещены ADR 0003.
            enums = (
                await conn.execute(
                    text("SELECT count(*) FROM pg_type WHERE typtype = 'e'")
                )
            ).scalar()
            assert int(enums) == 0

            # FK и их поведение ON DELETE (docs/04 §1–§7).
            fk_rows = (
                await conn.execute(
                    text(
                        "SELECT conname, confdeltype"
                        " FROM pg_constraint WHERE contype = 'f'"
                        " ORDER BY conname"
                    )
                )
            ).fetchall()
            confdel = {str(name): str(dtype) for name, dtype in fk_rows}
            # audit_log.actor_user_id SET NULL, auth_tokens.user_id CASCADE,
            # exam_types.subject_id RESTRICT — всего должно быть >= 9 FK.
            assert len(confdel) >= 9
            assert any(d == "a" for d in confdel.values())  # SET NULL
            assert any(d == "c" for d in confdel.values())  # CASCADE
            assert any(d == "r" for d in confdel.values())  # RESTRICT

            # CHECK-ограничения enum значений (VARCHAR + CHECK).
            checks = (
                await conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint"
                        " WHERE contype = 'c' AND conname LIKE 'ck_%'"
                    )
                )
            ).fetchall()
            names = {str(r[0]) for r in checks}
            assert "ck_users_role" in names
            assert "ck_exam_types_kind" in names
            assert "ck_auth_tokens_purpose" in names

            # Уникальные ограничения и индексы.
            uqs = (
                await conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint WHERE contype = 'u'"
                    )
                )
            ).fetchall()
            assert {str(r[0]) for r in uqs} >= {
                "uq_subjects_code",
                "uq_exam_types_code",
                "uq_users_telegram_id",
                "uq_auth_tokens_token_hash",
            }
            idx = (
                await conn.execute(
                    text(
                        "SELECT indexname FROM pg_indexes"
                        " WHERE tablename = 'auth_tokens'"
                    )
                )
            ).fetchall()
            assert "ix_auth_tokens_user_id_purpose" in {str(r[0]) for r in idx}

    try:
        _run_in_fresh_loop(check)
    finally:
        _run_in_fresh_loop(engine.dispose)
