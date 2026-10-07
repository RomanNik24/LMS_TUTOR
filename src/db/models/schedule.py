"""Модели расписания и уроков (docs/04 §3–§4): schedule_templates,
schedule_template_participants, lessons, lesson_participants.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, VARCHAR, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.enums import AttendanceStatus, LessonStatus
from src.db.base import Base
from src.db.mixins import TimestampMixin
from src.db.models._enum import enum_varchar

WEEKDAY_MIN = 1
WEEKDAY_MAX = 7
DEFAULT_DURATION_MINUTES = 60


class ScheduleTemplate(TimestampMixin, Base):
    """Шаблон «каждую неделю в это время» (docs/04 §3.1)."""

    __tablename__ = "schedule_templates"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    teacher_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="teacher_id"),
        nullable=False,
        comment="Преподаватель; FK → users, RESTRICT",
    )
    subject_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("subjects.id", ondelete="RESTRICT", name="subject_id"),
        nullable=False,
        comment="Предмет; FK → subjects, RESTRICT",
    )
    weekday: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="День недели ISO: 1 = понедельник … 7 = воскресенье"
    )
    start_local_time: Mapped[time] = mapped_column(
        Time(), nullable=False, comment="Локальное время начала (в поясе timezone)"
    )
    duration_minutes: Mapped[int] = mapped_column(
        SmallInteger,
        server_default=text(str(DEFAULT_DURATION_MINUTES)),
        nullable=False,
        comment="Длительность в минутах, CHECK > 0; по умолчанию 60",
    )
    timezone: Mapped[str] = mapped_column(
        VARCHAR(64), nullable=False, comment="IANA-пояс, в котором задано start_local_time"
    )
    starts_on: Mapped[date] = mapped_column(Date(), nullable=False, comment="Первая дата серии")
    ends_on: Mapped[date | None] = mapped_column(
        Date(), nullable=True, comment="Последняя дата серии; NULL — без конца"
    )
    is_active: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=text("true"),
        nullable=False,
        comment="false = пауза/отключение шаблона",
    )
    generated_until: Mapped[date | None] = mapped_column(
        Date(), nullable=True, comment="До какой даты уже сгенерированы уроки"
    )

    __table_args__ = (
        CheckConstraint(f"weekday BETWEEN {WEEKDAY_MIN} AND {WEEKDAY_MAX}", name="weekday_range"),
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
    )

    participants: Mapped[list["ScheduleTemplateParticipant"]] = relationship(
        back_populates="template", lazy="raise", viewonly=True
    )


class ScheduleTemplateParticipant(Base):
    """Участник шаблона (docs/04 §3.2); связующая таблица без временных колонок."""

    __tablename__ = "schedule_template_participants"

    template_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("schedule_templates.id", ondelete="CASCADE", name="template_id"),
        primary_key=True,
        comment="FK → schedule_templates, ON DELETE CASCADE",
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="student_id"),
        primary_key=True,
        comment="Ученик; FK → users, RESTRICT",
    )

    template: Mapped["ScheduleTemplate"] = relationship(back_populates="participants", lazy="raise")


class Lesson(TimestampMixin, Base):
    """Урок (docs/04 §4.1): разовый или созданный из шаблона."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    teacher_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="teacher_id"),
        nullable=False,
        comment="Кто проводит; FK → users, RESTRICT",
    )
    subject_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("subjects.id", ondelete="RESTRICT", name="subject_id"),
        nullable=False,
        comment="Предмет; FK → subjects, RESTRICT",
    )
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Начало (TIMESTAMPTZ, UTC)"
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Конец (TIMESTAMPTZ, UTC), CHECK > start_at",
    )
    status: Mapped[LessonStatus] = mapped_column(
        enum_varchar(LessonStatus, "status"),
        server_default=text("'scheduled'"),
        nullable=False,
        comment="scheduled | completed | cancelled (VARCHAR+CHECK)",
    )
    template_id: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("schedule_templates.id", ondelete="SET NULL", name="template_id"),
        nullable=True,
        comment="Из какого шаблона создан; при удалении шаблона — NULL",
    )
    is_detached: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=text("false"),
        nullable=False,
        comment="true = изменён вручную, шаблон его не трогает",
    )
    video_url_override: Mapped[str | None] = mapped_column(
        VARCHAR(500), nullable=True, comment="Переопределяет ссылку Телемоста из профиля"
    )
    board_url_override: Mapped[str | None] = mapped_column(
        VARCHAR(500), nullable=True, comment="Переопределяет ссылку на доску из профиля"
    )
    topic: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True, comment="Тема занятия")
    teacher_note: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="Приватная заметка преподавателя (ученик не видит)"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент отметки «проведён»"
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент отмены"
    )
    cancelled_by: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="SET NULL", name="cancelled_by"),
        nullable=True,
        comment="Кто отменил; при удалении аккаунта — NULL",
    )
    cancel_reason: Mapped[str | None] = mapped_column(
        VARCHAR(255), nullable=True, comment="Причина отмены"
    )

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="end_after_start"),
        UniqueConstraint("template_id", "start_at"),  # идемпотентность генерации
        # Преподаватель не ведёт два не отменённых урока одновременно (нужен btree_gist).
        ExcludeConstraint(
            ("teacher_id", "="),
            (text("tstzrange(start_at, end_at)"), "&&"),
            using="gist",
            where=text("status <> 'cancelled'"),
            name="ex_lessons_teacher_no_overlap",
        ),
        Index("ix_lessons_start_at", "start_at"),
        Index("ix_lessons_teacher_id_start_at", "teacher_id", "start_at"),
        Index("ix_lessons_status_start_at", "status", "start_at"),
    )

    participants: Mapped[list["LessonParticipant"]] = relationship(
        back_populates="lesson", lazy="raise", viewonly=True
    )


class LessonParticipant(Base):
    """Участник урока с посещаемостью и ценой (docs/04 §4.2); связующая таблица."""

    __tablename__ = "lesson_participants"

    lesson_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("lessons.id", ondelete="CASCADE", name="lesson_id"),
        primary_key=True,
        comment="FK → lessons, ON DELETE CASCADE",
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="student_id"),
        primary_key=True,
        comment="Ученик; FK → users, RESTRICT",
    )
    attendance: Mapped[AttendanceStatus] = mapped_column(
        enum_varchar(AttendanceStatus, "attendance"),
        server_default=text("'pending'"),
        nullable=False,
        comment="pending | attended | no_show | cancelled (VARCHAR+CHECK)",
    )
    is_billable: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=text("false"),
        nullable=False,
        comment="Засчитывается в заработок",
    )
    price_snapshot: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Цена, зафиксированная при отметке (рубли), CHECK >= 0; видит только owner",
    )

    __table_args__ = (
        CheckConstraint("price_snapshot >= 0", name="price_snapshot_nonneg"),
        Index("ix_lesson_participants_student_id_lesson_id", "student_id", "lesson_id"),
    )

    lesson: Mapped["Lesson"] = relationship(back_populates="participants", lazy="raise")
