"""Модель каталога услуг (docs/04 §1.4): catalog_items — витрина для гостей и учеников.

Карточки редактирует персонал; наружу отдаются только опубликованные, по возрастанию
``sort_order``. ``price_text`` — свободный текст («от 1500 ₽ за занятие»), а не число, поэтому
в финансовых данных он не участвует.

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from sqlalchemy import Identity, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import BIGINT, BOOLEAN, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.db.mixins import TimestampMixin


class CatalogItem(TimestampMixin, Base):
    """Карточка услуги в каталоге (docs/04 §1.4)."""

    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(
        BIGINT(), Identity(always=True), primary_key=True, comment="PK, BIGINT IDENTITY"
    )
    title: Mapped[str] = mapped_column(VARCHAR(150), nullable=False, comment="Название услуги")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="Описание")
    price_text: Mapped[str | None] = mapped_column(
        VARCHAR(100), nullable=True, comment="Стоимость свободным текстом, напр. «от 1500 ₽»"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False, comment="Порядок показа (меньше — выше)"
    )
    is_published: Mapped[bool] = mapped_column(
        BOOLEAN, server_default=text("false"), nullable=False, comment="Видна гостям и ученикам"
    )

    __table_args__ = (
        Index("ix_catalog_items_is_published_sort_order", "is_published", "sort_order"),
    )
