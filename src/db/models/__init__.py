"""SQLAlchemy 2.0 async-модели ядра схемы MY_LMS (задача T1.02).

Таблицы строго по ``docs/04_database_schema.md``: §0 (общие правила),
§1.1–1.3 (справочники), §2 (пользователи и доступ), §7.2 (журнал аудита).

Таблицы этапа 1 (расписание добавлено в T3.01, ``schedule.py``):
``subjects``, ``exam_types``, ``grade_scales``, ``users``,
``student_profiles``, ``student_subjects``, ``guardians``, ``auth_tokens``,
``audit_log``. Модели расписания, уроков, ДЗ, пробников, уведомлений и
витрины (``catalog_items``) — задачи последующих этапов; здесь их НЕТ
намеренно (требование T1.02 в docs/PLAN_FROM_SCRATCH.md).

Ключевые правила реализации:
- PK: ``BIGINT GENERATED ALWAYS AS IDENTITY``
  (``postgresql.BIGINT + sqlalchemy.Identity(always=True)``, docs/04 §0);
- время: ``TIMESTAMPTZ`` (``DateTime(timezone=True)``), хранится в UTC;
- ``JSONB`` для ``exam_types.config`` и ``audit_log.data``;
- ENUM — ``VARCHAR`` + ``CHECK`` без нативных типов PostgreSQL
  (``docs/adr/0003-enum-strategy.md``): ``sqlalchemy.Enum(...,
  native_enum=False, create_constraint=True, values_callable=...)``, список
  значений — из ``src/core/enums.py`` (единственный источник);
- связи объявлены с ``lazy="raise"``: неявная ленивая загрузка в async
  запрещена (docs/06, часть A2); для выборки связанных объектов
  репозитории будут использовать ``selectinload`` / ``joinedload``.

Допущения (зафиксированы и проверяются тестом tests/unit/test_models_schema.py):
- ON DELETE там, где docs/04 его не указал явно: перед удалением слой
  доступа проверяет зависимости, поэтому FK с ``RESTRICT`` — безопасный
  вариант по умолчанию; ``SET NULL`` — там, где docs допускает NULL после
  удаления связанной записи (создатель токена, аккаунт представителя в
  ``guardians.user_id``, автор события в ``audit_log``: журнал не теряет
  запись вместе с пользователем, docs/09 §6, §8);
- индексы: docs/04 требует явного индекса только для ``auth_tokens
  (user_id, purpose)``; уникальные колонки покрыты UNIQUE-индексами,
  lead-колонки составных ключей — PK/UNIQUE-индексами, остальные FK —
  индексами, которые PostgreSQL создаёт под внешние ключи автоматически;
  дублирующие индексы не создаются;
- CHECK-ограничения — ровно там, где они указаны в docs/04 (§1.3
  ``primary_score >= 0``, §2.2 ``lesson_price >= 0``); ограничения
  «на будущее» не добавляем (docs/06, часть F).

Комментарии и docstrings на русском согласно docs/06_agent_rules.md.
"""

from src.db.models._enum import enum_varchar
from src.db.models.audit import AuditLog
from src.db.models.catalog import CatalogItem
from src.db.models.exams import MockExamResult
from src.db.models.homework import (
    Homework,
    HomeworkAssignment,
    HomeworkExtension,
    HomeworkFile,
    HomeworkMaterial,
)
from src.db.models.notifications import Notification
from src.db.models.reference import ExamType, GradeScale, Subject
from src.db.models.schedule import (
    Lesson,
    LessonParticipant,
    ScheduleTemplate,
    ScheduleTemplateParticipant,
)
from src.db.models.users import AuthToken, Guardian, StudentProfile, StudentSubject, User

__all__ = [
    "CatalogItem",
    "AuditLog",
    "AuthToken",
    "ExamType",
    "GradeScale",
    "Guardian",
    "Homework",
    "HomeworkAssignment",
    "HomeworkExtension",
    "HomeworkFile",
    "HomeworkMaterial",
    "MockExamResult",
    "Lesson",
    "LessonParticipant",
    "Notification",
    "ScheduleTemplate",
    "ScheduleTemplateParticipant",
    "StudentProfile",
    "StudentSubject",
    "Subject",
    "User",
    "enum_varchar",
]
