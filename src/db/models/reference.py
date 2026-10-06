"""Модели справочников: subjects, exam_types, grade_scales (docs/04 §1.1–1.3).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Identity, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, JSONB, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.enums import ExamKind, ExamResultKind
from src.db.base import Base
from src.db.mixins import TimestampMixin
from src.db.models._enum import enum_varchar

if TYPE_CHECKING:
    from src.db.models.users import StudentSubject


class Subject(TimestampMixin, Base):
    """Справочник предметов (docs/04 §1.1)."""

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    code: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, comment="Машинный код: informatics, math"
    )
    name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False, comment="Отображаемое имя")
    is_active: Mapped[bool] = mapped_column(
        BOOLEAN, server_default=text("true"), nullable=False, comment="Предмет доступен для выбора"
    )

    __table_args__ = (UniqueConstraint("code"),)

    exam_types: Mapped[list["ExamType"]] = relationship(
        back_populates="subject", lazy="raise", viewonly=True
    )
    student_subject_links: Mapped[list["StudentSubject"]] = relationship(
        back_populates="subject", lazy="raise", viewonly=True
    )


class ExamType(TimestampMixin, Base):
    """Тип экзамена; на MVP ровно четыре записи (docs/04 §1.2)."""

    __tablename__ = "exam_types"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    code: Mapped[str] = mapped_column(
        VARCHAR(32),
        nullable=False,
        comment="Машинный код: oge_informatics, oge_math, ege_informatics, ege_math_profile",
    )
    subject_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("subjects.id", ondelete="RESTRICT", name="subject_id"),
        nullable=False,
        comment="FK → subjects (справочник не удаляют, пока на него есть ссылки)",
    )
    kind: Mapped[ExamKind] = mapped_column(
        enum_varchar(ExamKind, "kind"),
        nullable=False,
        comment="Вид экзамена: oge | ege (VARCHAR+CHECK)",
    )
    result_kind: Mapped[ExamResultKind] = mapped_column(
        enum_varchar(ExamResultKind, "result_kind"),
        nullable=False,
        comment="Результат шкалы: grade_2_5 | test_100 (VARCHAR+CHECK)",
    )
    max_primary: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Максимальный первичный балл текущего года"
    )
    name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False, comment="Отображаемое имя")
    config: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        server_default=text("'{}'"),
        nullable=False,
        comment="Особые правила, напр. {'min_geometry': 2} для ОГЭ математики",
    )
    is_active: Mapped[bool] = mapped_column(
        BOOLEAN, server_default=text("true"), nullable=False, comment="Тип доступен для выбора"
    )

    __table_args__ = (UniqueConstraint("code"),)

    subject: Mapped["Subject"] = relationship(back_populates="exam_types", lazy="raise")
    grade_scales: Mapped[list["GradeScale"]] = relationship(
        back_populates="exam_type", lazy="raise", viewonly=True
    )


class GradeScale(TimestampMixin, Base):
    """Шкала перевода первичного балла; одна строка на каждый балл (docs/04 §1.3)."""

    __tablename__ = "grade_scales"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    exam_type_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("exam_types.id", ondelete="CASCADE", name="exam_type_id"),
        nullable=False,
        comment="FK → exam_types, ON DELETE CASCADE (docs/04 §1.3)",
    )
    valid_year: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Год действия шкалы"
    )
    primary_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Первичный балл"
    )
    result_value: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Оценка 2–5 (ОГЭ) или тестовый балл 0–100 (ЕГЭ)",
    )

    __table_args__ = (
        UniqueConstraint("exam_type_id", "valid_year", "primary_score"),
        CheckConstraint("primary_score >= 0", name="primary_score_nonneg"),
    )

    exam_type: Mapped["ExamType"] = relationship(back_populates="grade_scales", lazy="raise")
