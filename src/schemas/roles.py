"""Приватность схем ответов по ролям (docs/08 §8, docs/09 §3, docs/01 §3).

Правила (docs/08 §8): в ответах для ученика НИКОГДА нет ``lesson_price``, ``price_snapshot``,
``is_billable``, ``teacher_notes``, ``teacher_note``, сумм и данных других учеников; в ответах для
менеджера нет ``lesson_price`` и финансовых блоков (``teacher_notes`` менеджеру доступны, docs/08 §8
и docs/01 §4.3). Эти поля не «скрываются условием»: для каждой роли заведена отдельная схема.

Схема, предназначенная для роли, помечается через ``audience_config``: метка ``x-audience``
попадает в OpenAPI, и тест приватности (``tests/unit/test_privacy_contract.py``) по ней отличает
схему владельца от схемы менеджера.
"""

from pydantic import ConfigDict

from src.core.enums import UserRole

AUDIENCE_KEY = "x-audience"

# Слова из имён полей, означающие деньги (имя поля делится по «_»): такие поля — только для owner.
FINANCE_TOKENS: frozenset[str] = frozenset(
    {
        "price",
        "amount",
        "amounts",
        "earned",
        "earnings",
        "expected",
        "revenue",
        "income",
        "billable",
        "balance",
        "payment",
        "payments",
        "salary",
        "finance",
        "finances",
        "financial",
        "money",
        "cost",
        "costs",
        "sum",
        "sums",
    }
)

# Поля, которые не видит ученик, но видит персонал (приватные заметки преподавателя).
STUDENT_HIDDEN_FIELDS: frozenset[str] = frozenset({"teacher_notes", "teacher_note"})

# Имена, содержащие «денежное» слово, но не являющиеся деньгами: ``price_text`` — свободный
# текст витрины каталога («от 1500 ₽»), он публичный (docs/04 §1.4).
FINANCE_NAME_EXCEPTIONS: frozenset[str] = frozenset({"price_text"})


def audience_config(role: UserRole, *, from_attributes: bool = True) -> ConfigDict:
    """Конфигурация схемы, предназначенной для роли (метка попадает в OpenAPI).

    Args:
        role: Роль, для которой предназначена схема.
        from_attributes: Разрешить построение из ORM-объектов.
    """
    return ConfigDict(json_schema_extra={AUDIENCE_KEY: role.value}, from_attributes=from_attributes)


def is_finance_field(name: str) -> bool:
    """Относится ли имя поля к деньгам (``lesson_price``, ``price_snapshot``, ``earned_month``…)."""
    if name in FINANCE_NAME_EXCEPTIONS:
        return False
    return any(token in FINANCE_TOKENS for token in name.lower().split("_"))
