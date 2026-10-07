"""Модели домашних заданий (docs/04 §5): homeworks, homework_materials,
homework_assignments, homework_extensions, homework_files.

Решения по docs/04 §0 и политике T1.02:
- ``created_at``/``updated_at`` — у ``homeworks`` и ``homework_assignments``; у журнала переносов и
  файлов выдачи только ``created_at`` (в docs/04 §5.4–5.5 так), у материалов временных колонок нет;
- ON DELETE там, где docs не указал явно: ``RESTRICT``, а для необязательных ссылок на
  пользователя (``graded_by``) — ``SET NULL``;
- индекс ``(homework_id)`` из docs/04 §5.3 не создаётся отдельно: его покрывает ведущая колонка
  ``UNIQUE (homework_id, student_id)``;
- «0 <= score <= max_score» проверяет сервис (docs/04 §5.3), в БД только ``score >= 0``.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkFileRole,
    HomeworkKind,
    SubmissionType,
)
from src.db.base import Base
from src.db.mixins import TimestampMixin
from src.db.models._enum import enum_varchar

MAX_EXTENSIONS = 2


class Homework(TimestampMixin, Base):
    """Само задание: общее для всех выданных учеников (docs/04 §5.1)."""

    __tablename__ = "homeworks"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    created_by: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="created_by"),
        nullable=False,
        comment="Кто создал; FK → users, RESTRICT",
    )
    lesson_id: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("lessons.id", ondelete="SET NULL", name="lesson_id"),
        nullable=True,
        comment="Урок, к которому привязано (необязательно); при удалении урока — NULL",
    )
    subject_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("subjects.id", ondelete="RESTRICT", name="subject_id"),
        nullable=False,
        comment="Предмет; FK → subjects, RESTRICT",
    )
    kind: Mapped[HomeworkKind] = mapped_column(
        enum_varchar(HomeworkKind, "kind"),
        nullable=False,
        comment="regular | mock_exam (VARCHAR+CHECK)",
    )
    exam_type_id: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("exam_types.id", ondelete="RESTRICT", name="exam_type_id"),
        nullable=True,
        comment="Тип экзамена; обязателен для mock_exam; FK → exam_types, RESTRICT",
    )
    title: Mapped[str] = mapped_column(VARCHAR(200), nullable=False, comment="Название задания")
    description: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="Инструкции к заданию"
    )
    max_score: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Макс. балл, CHECK > 0 (regular: число заданий)",
    )
    due_mode: Mapped[DueMode] = mapped_column(
        enum_varchar(DueMode, "due_mode"),
        nullable=False,
        comment="Как определён первоначальный дедлайн: next_lesson | fixed (VARCHAR+CHECK)",
    )

    __table_args__ = (
        CheckConstraint("max_score > 0", name="max_score_positive"),
        CheckConstraint(
            "kind <> 'mock_exam' OR exam_type_id IS NOT NULL", name="mock_exam_needs_exam_type"
        ),
    )

    materials: Mapped[list["HomeworkMaterial"]] = relationship(
        back_populates="homework", lazy="raise", viewonly=True
    )
    assignments: Mapped[list["HomeworkAssignment"]] = relationship(
        back_populates="homework", lazy="raise", viewonly=True
    )


class HomeworkMaterial(Base):
    """Файл преподавателя к заданию, например PDF (docs/04 §5.2)."""

    __tablename__ = "homework_materials"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    homework_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("homeworks.id", ondelete="CASCADE", name="homework_id"),
        nullable=False,
        comment="FK → homeworks, ON DELETE CASCADE",
    )
    s3_key: Mapped[str] = mapped_column(
        VARCHAR(500), nullable=False, comment="Ключ объекта в S3 (UUID, не имя файла)"
    )
    original_name: Mapped[str] = mapped_column(
        VARCHAR(255), nullable=False, comment="Исходное имя файла (только для показа)"
    )
    content_type: Mapped[str] = mapped_column(
        VARCHAR(100), nullable=False, comment="MIME-тип, определённый по содержимому"
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, comment="Размер файла, байты")

    homework: Mapped["Homework"] = relationship(back_populates="materials", lazy="raise")


class HomeworkAssignment(TimestampMixin, Base):
    """Выдача задания конкретному ученику со своим статусом и оценкой (docs/04 §5.3)."""

    __tablename__ = "homework_assignments"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    homework_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("homeworks.id", ondelete="CASCADE", name="homework_id"),
        nullable=False,
        comment="FK → homeworks, ON DELETE CASCADE",
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="student_id"),
        nullable=False,
        comment="Ученик; FK → users, RESTRICT",
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        enum_varchar(AssignmentStatus, "status"),
        server_default=text("'assigned'"),
        nullable=False,
        comment="assigned | submitted | needs_revision | graded | expired (VARCHAR+CHECK)",
    )
    original_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Первоначальный дедлайн (TIMESTAMPTZ)"
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Текущий дедлайн (TIMESTAMPTZ)"
    )
    extensions_count: Mapped[int] = mapped_column(
        SmallInteger,
        server_default=text("0"),
        nullable=False,
        comment="Количество переносов дедлайна, CHECK 0..2",
    )
    submission_type: Mapped[SubmissionType | None] = mapped_column(
        enum_varchar(SubmissionType, "submission_type"),
        nullable=True,
        comment="files | self_reported (VARCHAR+CHECK); NULL до сдачи",
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент сдачи"
    )
    score: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Балл (целое), CHECK >= 0; верхнюю границу проверяет сервис",
    )
    graded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент оценки"
    )
    graded_by: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="SET NULL", name="graded_by"),
        nullable=True,
        comment="Кто оценил; при удалении аккаунта — NULL",
    )
    graded_after_expiry: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=text("false"),
        nullable=False,
        comment="Оценено вручную уже после expired",
    )
    teacher_comment: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="Комментарий преподавателя"
    )
    student_comment: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="Комментарий ученика при сдаче"
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент перехода в expired"
    )

    __table_args__ = (
        UniqueConstraint("homework_id", "student_id"),
        CheckConstraint(
            f"extensions_count BETWEEN 0 AND {MAX_EXTENSIONS}", name="extensions_count_range"
        ),
        CheckConstraint("score >= 0", name="score_nonneg"),
        Index("ix_homework_assignments_student_id_status", "student_id", "status"),
        Index("ix_homework_assignments_status_due_at", "status", "due_at"),
    )

    homework: Mapped["Homework"] = relationship(back_populates="assignments", lazy="raise")
    extensions: Mapped[list["HomeworkExtension"]] = relationship(
        back_populates="assignment", lazy="raise", viewonly=True
    )
    files: Mapped[list["HomeworkFile"]] = relationship(
        back_populates="assignment", lazy="raise", viewonly=True
    )


class HomeworkExtension(Base):
    """Журнал переносов дедлайна (docs/04 §5.4): только добавление."""

    __tablename__ = "homework_extensions"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    assignment_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("homework_assignments.id", ondelete="CASCADE", name="assignment_id"),
        nullable=False,
        comment="FK → homework_assignments, ON DELETE CASCADE",
    )
    old_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Дедлайн до переноса"
    )
    new_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Дедлайн после переноса"
    )
    created_by: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="created_by"),
        nullable=False,
        comment="Кто перенёс (персонал); FK → users, RESTRICT",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Время записи (TIMESTAMPTZ, UTC)",
    )

    assignment: Mapped["HomeworkAssignment"] = relationship(
        back_populates="extensions", lazy="raise"
    )


class HomeworkFile(Base):
    """Файл выдачи: решение ученика или файл проверки преподавателя (docs/04 §5.5)."""

    __tablename__ = "homework_files"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    assignment_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("homework_assignments.id", ondelete="CASCADE", name="assignment_id"),
        nullable=False,
        comment="FK → homework_assignments, ON DELETE CASCADE",
    )
    uploaded_by: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="uploaded_by"),
        nullable=False,
        comment="Кто загрузил; FK → users, RESTRICT",
    )
    role: Mapped[HomeworkFileRole] = mapped_column(
        enum_varchar(HomeworkFileRole, "role"),
        nullable=False,
        comment="student_solution | teacher_review (VARCHAR+CHECK)",
    )
    s3_key: Mapped[str] = mapped_column(
        VARCHAR(500), nullable=False, comment="Ключ объекта в S3 (UUID, не имя файла)"
    )
    original_name: Mapped[str] = mapped_column(
        VARCHAR(255), nullable=False, comment="Исходное имя файла (только для показа)"
    )
    content_type: Mapped[str] = mapped_column(
        VARCHAR(100), nullable=False, comment="MIME-тип, определённый по содержимому"
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, comment="Размер файла, байты")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Время загрузки (TIMESTAMPTZ, UTC)",
    )

    assignment: Mapped["HomeworkAssignment"] = relationship(back_populates="files", lazy="raise")
