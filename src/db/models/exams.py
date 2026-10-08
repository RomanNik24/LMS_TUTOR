"""Модель результатов пробных экзаменов (docs/04 §6): mock_exam_results.

Единая таблица результатов пробников — из ДЗ типа ``mock_exam`` и введённых вручную на уроке.
Графики читают только её. Решения по политике T1.02:
- ON DELETE для ссылок на пользователей и тип экзамена — ``RESTRICT`` (docs/04 не уточняет), для
  необязательной ссылки на выдачу — ``SET NULL`` (как в docs/04 §6);
- проверку ``primary_score <= max_primary`` и правила конвертации выполняет сервис (docs/04 §6),
  в БД только ``primary_score >= 0``.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Identity, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.db.mixins import TimestampMixin


class MockExamResult(TimestampMixin, Base):
    """Результат пробного экзамена ученика (docs/04 §6.1)."""

    __tablename__ = "mock_exam_results"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="student_id"),
        nullable=False,
        comment="Ученик; FK → users, RESTRICT",
    )
    exam_type_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("exam_types.id", ondelete="RESTRICT", name="exam_type_id"),
        nullable=False,
        comment="Тип экзамена; FK → exam_types, RESTRICT",
    )
    exam_date: Mapped[date] = mapped_column(
        Date(), nullable=False, comment="Дата экзамена (по ней выбирается шкала по году)"
    )
    primary_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Первичный балл, >= 0"
    )
    max_primary: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Максимум этого варианта (снимок)"
    )
    geometry_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Баллы по геометрии: только ОГЭ математика"
    )
    converted_value: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Оценка 2–5 или тестовый балл; NULL, если шкала неприменима",
    )
    scale_year: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Год применённой шкалы"
    )
    assignment_id: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("homework_assignments.id", ondelete="SET NULL", name="assignment_id"),
        nullable=True,
        unique=True,
        comment="Выдача-источник (пробник был ДЗ); FK → homework_assignments, SET NULL, UNIQUE",
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Комментарий")
    created_by: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="created_by"),
        nullable=False,
        comment="Кто внёс или оценил (персонал); FK → users, RESTRICT",
    )

    __table_args__ = (
        CheckConstraint("primary_score >= 0", name="primary_score_non_negative"),
        Index(
            "ix_mock_exam_results_student_id_exam_type_id_exam_date",
            "student_id",
            "exam_type_id",
            "exam_date",
        ),
    )
