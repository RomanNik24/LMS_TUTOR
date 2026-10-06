"""Значения перечислений предметной области MY_LMS (задача T1.01).

Подход к ENUM утверждён в `docs/adr/0003-enum-strategy.md`: в PostgreSQL —
`VARCHAR` + `CHECK`, в SQLAlchemy — `Enum(..., native_enum=False)`.
Нативные типы ENUM PostgreSQL не используются.

Назначение этого модуля:
- Python-код (сервисы, схемы Pydantic) использует строковые значения
  (`UserRole.STUDENT.value` или `StrEnum`-экземпляр как строку);
- модели БД (задача T1.02) оборачивают эти классы в
  `sqlalchemy.Enum(cls, native_enum=False)` — тогда список значений CHECK-
  ограничения и допустимые значения в коде задаются одним источником;
- OpenAPI-схемы (docs/08) остаются строками с фиксированным набором значений.

Имена классов и значений соответствуют таблицам `docs/04_database_schema.md`;
ничего сверх документации здесь нет (docs/06, часть F).
"""

from enum import StrEnum


class ExamKind(StrEnum):
    """Вид экзамена: `exam_types.kind` (docs/04 §1.2)."""

    OGE = "oge"
    EGE = "ege"


class ExamResultKind(StrEnum):
    """Тип результата перевода по шкале: `exam_types.result_kind` (docs/04 §1.2)."""

    GRADE_2_5 = "grade_2_5"
    TEST_100 = "test_100"


class UserRole(StrEnum):
    """Роль пользователя: `users.role` (docs/04 §2.1, docs/09 §3)."""

    OWNER = "owner"
    MANAGER = "manager"
    STUDENT = "student"


class AuthTokenPurpose(StrEnum):
    """Назначение одноразового токена: `auth_tokens.purpose` (docs/04 §2.5)."""

    INVITE = "invite"
    WEB_LOGIN = "web_login"


class LessonStatus(StrEnum):
    """Статус урока: `lessons.status` (docs/04 §4.1)."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AttendanceStatus(StrEnum):
    """Посещаемость участника урока: `lesson_participants.attendance` (docs/04 §4.2)."""

    PENDING = "pending"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class HomeworkKind(StrEnum):
    """Вид домашнего задания: `homeworks.kind` (docs/04 §5.1)."""

    REGULAR = "regular"
    MOCK_EXAM = "mock_exam"


class DueMode(StrEnum):
    """Способ определения первоначального дедлайна: `homeworks.due_mode` (docs/04 §5.1)."""

    NEXT_LESSON = "next_lesson"
    FIXED = "fixed"


class AssignmentStatus(StrEnum):
    """Статус выдачи ДЗ ученику: `homework_assignments.status` (docs/04 §5.3)."""

    ASSIGNED = "assigned"
    SUBMITTED = "submitted"
    NEEDS_REVISION = "needs_revision"
    GRADED = "graded"
    EXPIRED = "expired"


class SubmissionType(StrEnum):
    """Тип сдачи работы: `homework_assignments.submission_type` (docs/04 §5.3)."""

    FILES = "files"
    SELF_REPORTED = "self_reported"


class HomeworkFileRole(StrEnum):
    """Назначение файла: `homework_files.role` (docs/04 §5.5)."""

    STUDENT_SOLUTION = "student_solution"
    TEACHER_REVIEW = "teacher_review"


class NotificationStatus(StrEnum):
    """Статус уведомления в outbox: `notifications.status` (docs/04 §7.1)."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


def values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    """Вернуть кортеж строковых значений enum.

    Нужен для явного построения CHECK-ограничений и тестов сверки со
    схемой (docs/04): значения в БД и в Python задаются одним источником.

    Args:
        enum_cls: Класс-перечисление из этого модуля.

    Returns:
        Кортеж значений в порядке объявления.
    """
    return tuple(member.value for member in enum_cls)
