"""Модели пользователей и доступа (docs/04 §2): users, student_profiles,
student_subjects, guardians, auth_tokens.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, CHAR, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.enums import AuthTokenPurpose, UserRole
from src.db.base import Base
from src.db.mixins import TimestampMixin
from src.db.models._enum import enum_varchar

if TYPE_CHECKING:
    from src.db.models.audit import AuditLog
    from src.db.models.reference import Subject


class User(TimestampMixin, Base):
    """Пользователь системы: owner / manager / student (docs/04 §2.1)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    role: Mapped[UserRole] = mapped_column(
        enum_varchar(UserRole, "role"),
        nullable=False,
        comment="Роль: owner | manager | student (VARCHAR+CHECK)",
    )
    telegram_id: Mapped[int | None] = mapped_column(
        BIGINT(),
        nullable=True,
        unique=True,
        comment=(
            "Telegram ID (BIGINT: значения > 2^31, docs/04 §0); NULL — профиль ждёт приглашение"
        ),
    )
    telegram_username: Mapped[str | None] = mapped_column(
        VARCHAR(64), nullable=True, comment="Для удобства отображения, не для идентификации"
    )
    display_name: Mapped[str] = mapped_column(
        VARCHAR(150), nullable=False, comment="Как обращаться к человеку"
    )
    timezone: Mapped[str] = mapped_column(
        VARCHAR(64),
        server_default=text("'Europe/Moscow'"),
        nullable=False,
        comment="IANA-часовой пояс пользователя",
    )
    is_active: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=text("true"),
        nullable=False,
        comment="false = архив (мягкое удаление, docs/04 §0)",
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент архивации (TIMESTAMPTZ)"
    )
    bot_blocked: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=text("false"),
        nullable=False,
        comment="Пользователь заблокировал бота",
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Последняя активность (TIMESTAMPTZ)"
    )

    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user",
        lazy="raise",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[StudentProfile.user_id]",
    )
    led_student_profiles: Mapped[list["StudentProfile"]] = relationship(
        back_populates="teacher",
        lazy="raise",
        viewonly=True,
        foreign_keys="[StudentProfile.teacher_id]",
    )
    student_subject_links: Mapped[list["StudentSubject"]] = relationship(
        back_populates="student", lazy="raise", viewonly=True
    )
    guardians: Mapped[list["Guardian"]] = relationship(
        back_populates="student",
        lazy="raise",
        viewonly=True,
        foreign_keys="[Guardian.student_id]",
    )
    linked_guardians: Mapped[list["Guardian"]] = relationship(
        back_populates="user",
        lazy="raise",
        viewonly=True,
        foreign_keys="[Guardian.user_id]",
    )
    auth_tokens: Mapped[list["AuthToken"]] = relationship(
        back_populates="user",
        lazy="raise",
        viewonly=True,
        foreign_keys="[AuthToken.user_id]",
    )
    created_tokens: Mapped[list["AuthToken"]] = relationship(
        back_populates="creator",
        lazy="raise",
        viewonly=True,
        foreign_keys="[AuthToken.created_by]",
    )
    audit_actions: Mapped[list["AuditLog"]] = relationship(
        back_populates="actor", lazy="raise", viewonly=True
    )


class StudentProfile(TimestampMixin, Base):
    """Профиль ученика, 1:1 с ``users`` при role = student (docs/04 §2.2)."""

    __tablename__ = "student_profiles"

    user_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="CASCADE", name="student_id"),
        primary_key=True,
        comment="PK и FK → users, ON DELETE CASCADE (docs/04 §2.2)",
    )
    teacher_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="RESTRICT", name="teacher_id"),
        nullable=False,
        comment=(
            "Ведущий преподаватель (owner/manager); RESTRICT — профиль всегда кому-то принадлежит"
        ),
    )
    school_class: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Класс (9, 11, …)"
    )
    lesson_price: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False,
        comment="Текущая цена занятия в рублях, CHECK >= 0; видит только owner (docs/09 §3)",
    )
    video_url: Mapped[str | None] = mapped_column(
        VARCHAR(500), nullable=True, comment="Постоянная ссылка Яндекс Телемоста"
    )
    board_url: Mapped[str | None] = mapped_column(
        VARCHAR(500), nullable=True, comment="Постоянная ссылка на онлайн-доску"
    )
    teacher_notes: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="Приватные заметки преподавателя (ученик не видит)"
    )

    __table_args__ = (CheckConstraint("lesson_price >= 0", name="lesson_price_nonneg"),)

    user: Mapped["User"] = relationship(
        back_populates="student_profile", lazy="raise", foreign_keys="[StudentProfile.user_id]"
    )
    teacher: Mapped["User"] = relationship(
        back_populates="led_student_profiles",
        lazy="raise",
        foreign_keys="[StudentProfile.teacher_id]",
    )


class StudentSubject(Base):
    """Связь многие-ко-многим ученик ↔ предмет (docs/04 §2.3).

    Связующая таблица: временных колонок нет (docs/04 §0), составной PK.
    """

    __tablename__ = "student_subjects"

    student_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="CASCADE", name="student_id"),
        primary_key=True,
        comment="FK → users (ученик), ON DELETE CASCADE",
    )
    subject_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("subjects.id", ondelete="CASCADE", name="subject_id"),
        primary_key=True,
        comment="FK → subjects, ON DELETE CASCADE (связь live-объектов, docs/04 §0)",
    )

    student: Mapped["User"] = relationship(back_populates="student_subject_links", lazy="raise")
    subject: Mapped["Subject"] = relationship(back_populates="student_subject_links", lazy="raise")


class Guardian(TimestampMixin, Base):
    """Родитель/законный представитель; задел, функционала в MVP нет (docs/04 §2.4)."""

    __tablename__ = "guardians"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="CASCADE", name="student_id_fk"),
        nullable=False,
        comment="FK → users (ученик), ON DELETE CASCADE (docs/04 §2.4)",
    )
    full_name: Mapped[str] = mapped_column(
        VARCHAR(150), nullable=False, comment="ФИО представителя"
    )
    relation: Mapped[str | None] = mapped_column(
        VARCHAR(50), nullable=True, comment="Кем приходится: мама, папа, …"
    )
    phone: Mapped[str | None] = mapped_column(
        VARCHAR(32), nullable=True, comment="Телефон (минимизация PII: необязательно, docs/09 §7)"
    )
    telegram_id: Mapped[int | None] = mapped_column(
        BIGINT(), nullable=True, comment="Telegram ID представителя (BIGINT, docs/04 §0)"
    )
    user_id: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="SET NULL", name="linked_user_id_fk"),
        nullable=True,
        comment="Для будущей роли parent; колонка NULL-допустима, при удалении аккаунта — NULL",
    )

    student: Mapped["User"] = relationship(
        back_populates="guardians", lazy="raise", foreign_keys="[Guardian.student_id]"
    )
    user: Mapped["User | None"] = relationship(
        back_populates="linked_guardians", lazy="raise", foreign_keys="[Guardian.user_id]"
    )


class AuthToken(TimestampMixin, Base):
    """Приглашения и одноразовые ссылки входа (docs/04 §2.5, docs/09 §2).

    Хранится только SHA-256 хэш токена; сам токен — нет. Токен действителен,
    если ``used_at IS NULL AND revoked_at IS NULL AND expires_at > now()``.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    purpose: Mapped[AuthTokenPurpose] = mapped_column(
        enum_varchar(AuthTokenPurpose, "purpose"),
        nullable=False,
        comment="Назначение: invite | web_login (VARCHAR+CHECK)",
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="CASCADE", name="user_id"),
        nullable=False,
        comment="Для кого токен; FK → users, ON DELETE CASCADE (токен без владельца не нужен)",
    )
    token_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False,
        unique=True,
        comment="SHA-256 от токена (64 hex-символа); сам токен не хранится (docs/09 §2.1)",
    )
    created_by: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="SET NULL", name="created_by"),
        nullable=True,
        comment="Кто создал; NULL для web_login; при удалении создателя — NULL",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Срок действия: invite +7 дней, web_login +10 минут (TIMESTAMPTZ)",
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент погашения (одноразовость)"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент отзыва"
    )

    __table_args__ = (Index("ix_auth_tokens_user_id_purpose", "user_id", "purpose"),)

    user: Mapped["User"] = relationship(
        back_populates="auth_tokens", lazy="raise", foreign_keys="[AuthToken.user_id]"
    )
    creator: Mapped["User | None"] = relationship(
        back_populates="created_tokens", lazy="raise", foreign_keys="[AuthToken.created_by]"
    )
