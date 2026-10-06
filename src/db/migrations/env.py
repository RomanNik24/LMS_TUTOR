"""Окружение Alembic для миграций MY_LMS (задача T1.03).

Настройки (по docs/03 «Миграции», ADR 0002 и ADR 0003):

- ``script_location = src/db/migrations`` задаётся в ``alembic.ini`` в корне;
- подключение — асинхронное SQLAlchemy (asyncpg), строка ``DATABASE_URL``
  берётся из ``Settings`` приложения (``src/core/config.py``), секреты
  в Git не хранятся;
- ``compare_type=True`` — autogenerate замечает смену типов колонок;
- metadata моделей T1.02 (``src.db.models``) подключена для autogenerate;
- соглашение об именах ограничений (``NAMING_CONVENTION``) определено в
  ``src/db/base.py`` и применяется через metadata — имена PK/FK/UNIQUE/CHECK/
  INDEX детерминированы и совпадают в моделях и БД;
- ENUM — только ``VARCHAR`` + ``CHECK`` (ADR 0003); нативные PostgreSQL ENUM
  не создаются, поэтому специальной блокировки вывода типов не требуется.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import Settings
from src.db import models  # noqa: F401  (регистрирует таблицы T1.02 в Base.metadata)
from src.db.base import Base

# Импорт модуля моделей регистрирует все таблицы этапа T1.02 в Base.metadata
# (autogenerate должен видеть ВСЕ модели).

# Конфигурация логирования из alembic.ini (если доступна).
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Строка подключения — из настроек приложения (DATABASE_URL, asyncpg).
# Alembic получает её здесь, а не из alembic.ini: секрет не попадает в Git.
settings = Settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Metadata моделей — цель для autogenerate.
target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Хук Alembic: не даём autogenerate трогать служебные объекты.

    ENUM-колонки моделируются как VARCHAR + именованный CheckConstraint
    (ADR 0003), поэтому нативные типы/индексы-кандидаты из reflection в diff
    не нужны; имена ограничений полностью определяет NAMING_CONVENTION.
    """
    # Нативные PostgreSQL ENUM запрещены ADR 0003 — игнорируем их в diff.
    if type_ == "type":
        return False
    return True


def run_migrations_offline() -> None:
    """Запуск миграций в «offline»-режиме (генерация SQL без подключения).

    В этом режиме Alembic не открывает соединение с базой, а выводит SQL
    инструкций в stdout; URL всё равно нужен для диалекта и цитирования.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Сравнивать типы колонок при autogenerate (требование задачи T1.03).
        compare_type=True,
        # Сверять значения по умолчанию по умолчанию (дрейф server_default).
        compare_server_default=True,
        # Фильтр служебных объектов diff (ADR 0003) — см. _include_object.
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Выполнить миграции в уже открытом синхронном соединении."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Фильтр служебных объектов diff (ADR 0003) — см. _include_object.
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Создать async-движок (asyncpg) и выполнить миграции внутри события."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Запуск миграций в «online»-режиме через асинхронный движок."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
