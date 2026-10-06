"""Модель журнала аудита audit_log (docs/04 §7.2).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Identity, func, text
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.users import User


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
