"""Пакет моделей и инфраструктуры БД MY_LMS (задача T1.02).

Модели SQLAlchemy 2.0 — в ``src.db.models``; базовый класс и соглашение
об именах ограничений — в ``src.db.base``; миксины колонок — в
``src.db.mixins``. Миграции Alembic появятся в T1.03 (docs/adr/0002:
ревизии живут в ``src/db/migrations/``).

Экспорт имён здесь даёт гарантию: ``from src.db.models import *`` и
``import src.db`` выполняются без ошибок на чистом Python-окружении.
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
