"""SQLAlchemy 2.0 async-модели ядра схемы MY_LMS (задача T1.02).

Таблицы строго по ``docs/04_database_schema.md``: §0 (общие правила),
§1.1–1.3 (справочники), §2 (пользователи и доступ), §7.2 (журнал аудита).

Созданы ТОЛЬКО девять таблиц текущего этапа:
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
  native_enum=False, create_constraint=True)``, список значений — из
  ``src/core/enums.py`` (единственный источник);
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

from datetime import datetime
from enum import StrEnum

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
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, CHAR, JSONB, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.enums import AuthTokenPurpose, ExamKind, ExamResultKind, UserRole
from src.db.base import Base
from src.db.mixins import TimestampMixin


def enum_varchar(enum_cls: type[StrEnum], constraint_name: str) -> CheckConstraint:
    """Возвращает ограничение «допустимые значения enum» (ADR 0003).

    Физический тип колонки при этом — обычный ``VARCHAR`` нужной длины;
    список значений фиксируется явным ``CheckConstraint`` с именем из
    ``NAMING_CONVENTION`` (итог: ``ck_<таблица>_<constraint_name>``).

    Args:
        enum_cls: Класс-перечисление из ``src/core/enums.py`` — единственный
            источник списка значений для Python и для БД.
        constraint_name: короткое имя ограничения без префикса таблицы
            (например ``"role"`` → ``ck_users_role``).

    Returns:
        Готовое ограничение для ``__table_args__`` модели.
    """
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    # Имя колонки подставляется через токен %(column_0_name)s: SQLAlchemy
    # раскроет его в физическое имя колонки при компиляции DDL (например,
    # "users.role IN (...)"). Ограничение привязано к первой колонке, на
    # которую оно ссылается (ADR 0003: VARCHAR + CHECK вместо нативного ENUM).
    return CheckConstraint(
        f"%(column_0_name)s IN ({values})",
        name=constraint_name,
        _create_rule=_skip_if_existing_named_constraint,
    )


def _skip_if_existing_named_constraint(inspector, table_name: str) -> bool:
    """Правило автогенерации Alembic: не создавать дубли enum-CHECK ограничений.

    SQLAlchemy при reflection не сопоставляет отражённые CHECK-ограничения
    с объектами метаданных (у отражённых имён нет), поэтому autogenerate
    может повторно предложить уже существующее в БД ограничение — PostgreSQL
    откажет с DuplicateObjectError. Если в таблице уже есть CHECK вида
    ``<колонка> IN ('...', '...')`` (т.е. enum-CHECK создан ранее), повторное
    добавление пропускаем. При создании таблиц с нуля (upgrade head на пустой
    БД) ограничения создаются обычным порядком — правило влияет только на
    autogenerate diff против живой схемы.
    """
    try:
        reflected = inspector.get_check_constraints(table_name)
    except Exception:  # pragma: no cover - отказ инспектора не блокирует diff
        return True
    for const in reflected:
        check_text = (const.get("check") or "").lower()
        if " in " in check_text and "'" in check_text:
            # В таблице уже присутствует enum-CHECK («колонка IN ('значения')»)
            # — новое ограничение с тем же смыслом добавлять не нужно.
            return False
    return True


def enum_column_type(enum_cls: type[StrEnum]) -> VARCHAR:
    """VARCHAR-тип для enum-колонки (значения проверяет enum_varchar).

    Нативный PostgreSQL ENUM не создаётся (ADR 0003): CHECK эмулирует
    перечисление на уровне БД, а колонка остаётся строкой.

    Args:
        enum_cls: Класс-перечисление из ``src/core/enums.py``.

    Returns:
        Тип ``VARCHAR`` с длиной по самому длинному значению enum.
    """
    return VARCHAR(max(len(member.value) for member in enum_cls))


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

    # UNIQUE code (docs/04 §1.1). Отдельный индекс не нужен: уникальный индекс
    # от UNIQUE покрывает поиск по code. Имя даёт NAMING_CONVENTION:
    # uq_subjects_code (имя-колоночный плейсхолдер «code» недопустим — в БД
    # имена ограничений уникальны в схеме, см. ADR 0002).
    __table_args__ = (UniqueConstraint("code"),)

    # Связи; lazy="raise" — см. docstring модуля.
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
        enum_column_type(ExamKind),
        nullable=False,
        comment="Вид экзамена: oge | ege (VARCHAR+CHECK)",
    )
    result_kind: Mapped[ExamResultKind] = mapped_column(
        enum_column_type(ExamResultKind),
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

    __table_args__ = (
        # ENUM → VARCHAR + CHECK (ADR 0003): имена даёт NAMING_CONVENTION —
        # ck_exam_types_kind, ck_exam_types_result_kind.
        enum_varchar(ExamKind, "kind"),
        enum_varchar(ExamResultKind, "result_kind"),
        UniqueConstraint("code"),
    )

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
        # Имя ограничения формирует NAMING_CONVENTION:
        # uq_grade_scales_exam_type_id_valid_year_primary_score.
        UniqueConstraint("exam_type_id", "valid_year", "primary_score"),
        CheckConstraint("primary_score >= 0", name="primary_score_nonneg"),
        # Lead-колонка exam_type_id покрыта уникальным индексом выше.
    )

    exam_type: Mapped["ExamType"] = relationship(back_populates="grade_scales", lazy="raise")


class User(TimestampMixin, Base):
    """Пользователь системы: owner / manager / student (docs/04 §2.1)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    role: Mapped[UserRole] = mapped_column(
        enum_column_type(UserRole),
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

    # telegram_id объявлен с unique=True — UNIQUE-ограничение users_telegram_id_key
    # с многократными NULL (docs/04 §2.1).

    # 1:1 профиль ученика; cascade — профиль живёт вместе с пользователем.
    __table_args__ = (
        # ENUM → VARCHAR + CHECK (ADR 0003): имя даёт NAMING_CONVENTION —
        # ck_users_role.
        enum_varchar(UserRole, "role"),
    )

    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user",
        lazy="raise",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[StudentProfile.user_id]",
    )
    # Обратная сторона ведущего преподавателя у профилей учеников.
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
        # Имя ограничения уникально в таблице guardians: оба FK ссылаются на
        # users.id, поэтому колонки различаются суффиксом (student / linked).
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
        enum_column_type(AuthTokenPurpose),
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

    __table_args__ = (
        # ENUM → VARCHAR + CHECK (ADR 0003): имя даёт NAMING_CONVENTION —
        # ck_auth_tokens_purpose.
        enum_varchar(AuthTokenPurpose, "purpose"),
        # token_hash объявлен с unique=True — UNIQUE-ограничение uq_auth_tokens_token_hash.
        # Явный индекс (user_id, purpose) — требование docs/04 §2.5.
        Index("ix_auth_tokens_user_id_purpose", "user_id", "purpose"),
    )

    user: Mapped["User"] = relationship(
        back_populates="auth_tokens", lazy="raise", foreign_keys="[AuthToken.user_id]"
    )
    creator: Mapped["User | None"] = relationship(
        back_populates="created_tokens", lazy="raise", foreign_keys="[AuthToken.created_by]"
    )


class AuditLog(Base):
    """Журнал аудита чувствительных действий (docs/04 §7.2, docs/09 §6).

    Журнал: по docs/04 §0 есть только ``created_at`` (без ``updated_at``);
    записи неизменяемы — обновления и удаления из слоя доступа не выполняются.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="SET NULL", name="actor_user_id"),
        nullable=True,
        comment="Кто выполнил действие; журнал сохраняется при удалении пользователя (docs/09 §8)",
    )
    action: Mapped[str] = mapped_column(
        VARCHAR(80),
        nullable=False,
        comment="lesson.rescheduled, student.price_changed, invite.created, …",
    )
    entity_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False, comment="Тип сущности")
    entity_id: Mapped[int | None] = mapped_column(
        BIGINT(), nullable=True, comment="ID сущности (NULL — если сущность удалена)"
    )
    data: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'"), nullable=False, comment="Было/стало"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Момент события (TIMESTAMPTZ); единственная временная колонка журнала",
    )

    actor: Mapped["User | None"] = relationship(back_populates="audit_actions", lazy="raise")
