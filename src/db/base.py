"""Базовый класс декларативных моделей SQLAlchemy 2.0 (задача T1.02).

Единая точка определения ``Base`` и соглашения об именах ограничений.
Alembic-миграции (задача T1.03) используют этот же ``NAMING_CONVENTION``,
чтобы имена PK/FK/UNIQUE/CHECK/INDEX были детерминированными и совпадали
в БД с описанием в моделях (требование docs/03 к миграциям).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from typing import ClassVar

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Соглашение об именах ограничений PostgreSQL (стандартные ключи SQLAlchemy
# %(table_name)s и т.п.), чтобы Alembic autogenerate корректно сравнивал
# ограничения со схемой и имена были детерминированными.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(constraint_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей проекта MY_LMS.

    Наследники описывают таблицы схемы ``docs/04_database_schema.md``.
    Модели рассчитаны на ``AsyncSession``; связи объявлены с
    ``lazy="raise"``, поэтому неявных ленивых загрузок нет (docs/06, A2).
    """

    metadata: ClassVar[MetaData] = MetaData(naming_convention=NAMING_CONVENTION)
