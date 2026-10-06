"""Помощник объявления ENUM-колонок (VARCHAR + CHECK, ADR 0003).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from enum import StrEnum
from typing import TypeVar

from sqlalchemy import Enum as SqlEnum

EnumType = TypeVar("EnumType", bound=StrEnum)


def _enum_values(enum_cls: type[EnumType]) -> list[str]:
    """Вернуть строковые значения enum в порядке объявления."""

    return [member.value for member in enum_cls]


def enum_varchar(enum_cls: type[EnumType], constraint_name: str) -> SqlEnum:
    """Вернуть non-native SQLAlchemy Enum с VARCHAR + CHECK (ADR 0003).

    ``native_enum=False`` гарантирует физический тип VARCHAR вместо
    PostgreSQL ENUM. ``create_constraint=True`` создаёт DB-level CHECK.
    ``values_callable`` сохраняет именно ``member.value`` — то есть
    согласованные lowercase-значения из ``src/core/enums.py``.

    ``constraint_name`` передаётся в SQLAlchemy Enum как имя type-bound CHECK.
    При ``NAMING_CONVENTION`` из ``src/db/base.py`` итоговое имя будет
    ``ck_<table>_<constraint_name>``.

    Args:
        enum_cls: Класс-перечисление из ``src/core/enums.py``.
        constraint_name: Имя CHECK без префикса таблицы.

    Returns:
        Non-native SQLAlchemy Enum, компилируемый в VARCHAR + CHECK.
    """
    return SqlEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        values_callable=_enum_values,
        length=max(len(member.value) for member in enum_cls),
        name=constraint_name,
    )
