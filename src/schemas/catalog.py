"""Схемы каталога услуг (docs/08 §3 и §5.7, docs/04 §1.4).

Публичная схема (``CatalogItemPublic``) не содержит служебных полей; персонал видит порядок и
признак публикации. ``price_text`` — свободный текст витрины, а не число.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core import texts

TITLE_MAX_LENGTH = 150
DESCRIPTION_MAX_LENGTH = 5000
PRICE_TEXT_MAX_LENGTH = 100
SORT_ORDER_MAX = 1_000_000
REORDER_MAX_ITEMS = 200


def _clean(value: str) -> str:
    return value.strip()


class CatalogItemPublic(BaseModel):
    """Карточка опубликованной услуги."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    price_text: str | None


class CatalogItemAdmin(CatalogItemPublic):
    """Карточка для персонала: порядок и публикация."""

    sort_order: int
    is_published: bool


class CatalogCreate(BaseModel):
    """Создание карточки. Порядок по умолчанию — в конец списка."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    price_text: str | None = Field(default=None, max_length=PRICE_TEXT_MAX_LENGTH)
    is_published: bool = False

    @field_validator("title", "description")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = _clean(value)
        if not cleaned:
            raise ValueError(texts.CATALOG_FIELD_BLANK)
        return cleaned

    @field_validator("price_text")
    @classmethod
    def _price(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else value.strip()


class CatalogUpdate(BaseModel):
    """Правка карточки; ``price_text`` можно очистить, передав ``null``."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    price_text: str | None = Field(default=None, max_length=PRICE_TEXT_MAX_LENGTH)
    sort_order: int | None = Field(default=None, ge=0, le=SORT_ORDER_MAX)
    is_published: bool | None = None

    @field_validator("title", "description")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean(value)
        if not cleaned:
            raise ValueError(texts.CATALOG_FIELD_BLANK)
        return cleaned

    @field_validator("price_text")
    @classmethod
    def _price(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else value.strip()

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(texts.STUDENT_UPDATE_EMPTY)
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError(texts.STUDENT_FIELD_NOT_NULLABLE)
        if "description" in self.model_fields_set and self.description is None:
            raise ValueError(texts.STUDENT_FIELD_NOT_NULLABLE)
        if "sort_order" in self.model_fields_set and self.sort_order is None:
            raise ValueError(texts.STUDENT_FIELD_NOT_NULLABLE)
        if "is_published" in self.model_fields_set and self.is_published is None:
            raise ValueError(texts.STUDENT_FIELD_NOT_NULLABLE)
        return self


class CatalogReorder(BaseModel):
    """Новый порядок: идентификаторы всех карточек сверху вниз."""

    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(min_length=1, max_length=REORDER_MAX_ITEMS)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError(texts.CATALOG_REORDER_INVALID)
        return self
