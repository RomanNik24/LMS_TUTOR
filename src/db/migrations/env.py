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
  не создаются.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import Settings
from src.db import models  # noqa: F401  (регистрирует таблицы T1.02 в Base.metadata)
from src.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _load_settings() -> Settings:
    """Загрузить настройки для Alembic без зависимости от Redis.

    Alembic использует только DATABASE_URL, поэтому в local/staging отсутствие
    REDIS_URL или DEFAULT_TIMEZONE не должно мешать миграциям. Production не
    получает ослабления: там используется полный ``Settings()`` со всеми
    штатными проверками приложения.
    """
    if os.environ.get("APP_ENV") == "prod":
        # Prod: обязательные поля приходят из окружения (docs/02 §7).
        return Settings()  # type: ignore[call-arg]

    database_url = os.environ.get("DATABASE_URL")
    if database_url is None:
        # Local/staging: значения полей берутся из .env.local (ENV_FILE_NAME).
        return Settings()  # type: ignore[call-arg]

    return Settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        default_timezone=os.environ.get("DEFAULT_TIMEZONE", "UTC"),
    )


settings = _load_settings()

# Config использует ConfigParser-интерполяцию. Процентные escape-последовательности
# в URL нужно удвоить до передачи в set_main_option.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Запуск миграций в offline-режиме."""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
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
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Создать async-движок и выполнить миграции."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Запуск миграций в online-режиме через асинхронный движок."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
