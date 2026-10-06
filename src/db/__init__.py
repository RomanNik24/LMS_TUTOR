"""Пакет моделей и инфраструктуры БД MY_LMS.

Модели SQLAlchemy 2.0 — в ``src.db.models``; базовый класс и соглашение
об именах ограничений — в ``src.db.base``; миксины колонок — в
``src.db.mixins``. Миграции Alembic находятся в
``src/db/migrations/`` согласно ADR 0002.

Экспорт имён здесь даёт гарантию: ``import src.db`` выполняется без ошибок
и предоставляет основной набор объектов модели для инфраструктуры проекта.
"""

from src.db.base import NAMING_CONVENTION, Base
from src.db.mixins import TimestampMixin
from src.db.models import (
    AuditLog,
    AuthToken,
    ExamType,
    GradeScale,
    Guardian,
    StudentProfile,
    StudentSubject,
    Subject,
    User,
    enum_varchar,
)

__all__ = [
    "NAMING_CONVENTION",
    "AuditLog",
    "AuthToken",
    "Base",
    "ExamType",
    "GradeScale",
    "Guardian",
    "StudentProfile",
    "StudentSubject",
    "Subject",
    "TimestampMixin",
    "User",
    "enum_varchar",
]
