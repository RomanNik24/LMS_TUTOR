"""Схемы аутентификации и профиля (docs/08 §2)."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.enums import UserRole

DISPLAY_NAME_MAX_LENGTH = 150


class TelegramLoginRequest(BaseModel):
    """Тело ``POST /auth/telegram``: сырые ``initData`` Mini App."""

    model_config = ConfigDict(extra="forbid")

    init_data: str = Field(min_length=1, max_length=8192)


class LinkLoginRequest(BaseModel):
    """Тело ``POST /auth/link``: токен одноразовой ссылки входа."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)


class MeResponse(BaseModel):
    """Текущий пользователь (docs/08 §2): id, роль, имя, часовой пояс.

    Цен, заметок и финансов здесь нет и быть не должно (docs/09 §3).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    display_name: str
    timezone: str


class MeUpdateRequest(BaseModel):
    """Тело ``PATCH /me``: можно менять только ``timezone`` и ``display_name``."""

    model_config = ConfigDict(extra="forbid")

    timezone: str | None = None
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX_LENGTH)

    @field_validator("timezone")
    @classmethod
    def _timezone_is_iana(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(
                "Неизвестный часовой пояс (нужен IANA, например Europe/Moscow)"
            ) from error
        return value

    @field_validator("display_name")
    @classmethod
    def _display_name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Имя не может быть пустым")
        return stripped

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "MeUpdateRequest":
        if self.timezone is None and self.display_name is None:
            raise ValueError("Укажите timezone или display_name")
        return self
