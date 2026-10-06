"""Базовый класс декларативных моделей SQLAlchemy 2.0 (задача T1.02).

Единая точка определения ``Base`` и соглашения об именах ограничений.
Alembic-миграции (задача T1.03) используют этот же ``NAMING_CONVENTION``,
чтобы имена PK/FK/UNIQUE/CHECK/INDEX были детерминированными и совпадали
в БД с описанием в моделях (требование docs/03 к миграциям).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Соглашение об именах ограничений PostgreSQL. Шаблоны с {table} нужны,
# чтобы Alembic autogenerate корректно сравнивал ограничения со схемой.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_{table}_{column_names}",
    "uq": "uq_{table}_{column_names}",
    "ck": "ck_{table}_{constraint_name}",
    "fk": "fk_{table}_{constraint_name}",
    "pk": "pk_{table}",
}


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей проекта MY_LMS.

    Наследники описывают таблицы схемы ``docs/04_database_schema.md``.
    Модели рассчитаны на ``AsyncSession``; связи объявлены с
    ``lazy="raise"``, поэтому неявных ленивых загрузок нет (docs/06, A2).
    """

    metadata: MetaData = MetaData(naming_convention=NAMING_CONVENTION)
