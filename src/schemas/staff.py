"""Схемы сотрудников (docs/04 §2.1, docs/08 §5.3, T2.03): только для владельца."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core import texts
from src.core.constants import DEFAULT_USER_TIMEZONE
from src.core.enums import UserRole
from src.schemas.auth import DISPLAY_NAME_MAX_LENGTH
from src.schemas.roles import audience_config
from src.schemas.validators import clean_name, iana_timezone

# Сотрудником может быть только владелец или менеджер; ученика этим сервисом не создать.
StaffRole = Literal[UserRole.OWNER, UserRole.MANAGER]


class StaffCreate(BaseModel):
    """Создание профиля сотрудника (``POST /admin/staff``): Telegram привязывается приглашением."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    role: StaffRole = UserRole.MANAGER
    timezone: str = DEFAULT_USER_TIMEZONE

    _name = field_validator("display_name")(clean_name)
    _tz = field_validator("timezone")(iana_timezone)


class StaffUpdate(BaseModel):
    """Изменение имени и/или роли сотрудника (``PATCH /admin/staff/{id}``)."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    role: StaffRole | None = None

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else clean_name(value)

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(texts.STUDENT_UPDATE_EMPTY)
        for name in ("display_name", "role"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name}: {texts.STUDENT_FIELD_NOT_NULLABLE}")
        return self


class StaffItem(BaseModel):
    """Сотрудник в списке и карточке: роль, статус, привязка Telegram и ожидание приглашения."""

    model_config = audience_config(UserRole.OWNER)

    user_id: int
    display_name: str
    role: UserRole
    timezone: str
    is_active: bool
    bot_blocked: bool
    telegram_linked: bool
    invite_pending: bool
