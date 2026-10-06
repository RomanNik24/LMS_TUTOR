"""Общие миксины колонок SQLAlchemy 2.0 (задача T1.02).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Колонки ``created_at`` / ``updated_at`` (docs/04 §0).

    Применяется ко всем таблицам этапа T1.02, КРОМЕ:
    - ``audit_log`` — журнал: по docs/04 §7.2 содержит только ``created_at``;
    - ``student_subjects`` — связующая таблица: временных колонок в docs/04 §2.3
      нет, составной PK.

    Значения по умолчанию задаются на стороне PostgreSQL (``now()``), чтобы
    колонки заполнялись при любой вставке (ORM, Core, прямой SQL).
    ``updated_at`` обновляется в приложении (docs/04 §0); триггеров в схеме нет.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Время создания записи (TIMESTAMPTZ, UTC; docs/04 §0)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Время последнего изменения; обновляется в приложении (docs/04 §0)",
    )
