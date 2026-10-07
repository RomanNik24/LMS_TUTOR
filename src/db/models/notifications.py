"""Модель outbox уведомлений notifications (docs/04 §7.1, docs/05 §6).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, Index, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, JSONB, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from src.core.enums import NotificationStatus
from src.db.base import Base
from src.db.mixins import TimestampMixin
from src.db.models._enum import enum_varchar


class Notification(TimestampMixin, Base):
    """Уведомление в очереди отправки (схема outbox).

    Сервисы только кладут записи в эту таблицу в одной транзакции с бизнес-изменением; отправку
    выполняет воркер. ``dedup_key`` уникален: повторная постановка того же события не создаёт
    дубль. Диспетчер берёт записи ``pending`` с ``scheduled_for <= now`` (индекс по этим полям).
    """

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_status_scheduled_for", "status", "scheduled_for"),)

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT(),
        ForeignKey("users.id", ondelete="CASCADE", name="user_id"),
        nullable=False,
        comment="Получатель; при удалении пользователя его очередь удаляется",
    )
    type: Mapped[str] = mapped_column(
        VARCHAR(50),
        nullable=False,
        comment="Тип уведомления (lesson_reminder, homework_graded, …), список в docs/05 §6",
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        server_default=text("'{}'"),
        nullable=False,
        comment="Данные для шаблона: id сущностей и значения",
    )
    dedup_key: Mapped[str] = mapped_column(
        VARCHAR(200), unique=True, nullable=False, comment="Ключ дедупликации, UNIQUE"
    )
    is_urgent: Mapped[bool] = mapped_column(
        BOOLEAN,
        server_default=text("false"),
        nullable=False,
        comment="Срочное: игнорирует тихие часы",
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Не раньше этого момента (TIMESTAMPTZ)"
    )
    status: Mapped[NotificationStatus] = mapped_column(
        enum_varchar(NotificationStatus, "status"),
        server_default=text("'pending'"),
        nullable=False,
        comment="pending | sent | failed | skipped (VARCHAR+CHECK)",
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, server_default=text("0"), nullable=False, comment="Число попыток отправки"
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Момент успешной отправки"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="Текст последней ошибки отправки"
    )
