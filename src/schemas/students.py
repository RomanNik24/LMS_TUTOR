"""Схемы карточки ученика по ролям (docs/04 §2.2, docs/08 §8, T2.01).

Три отдельные схемы вместо одной со скрытием полей:
- ``StudentSelfProfile`` — ученик о себе: без цены, заметок и финансов;
- ``StudentCardManager`` — менеджер: заметки преподавателя есть, цены и финансов нет;
- ``StudentCardOwner`` — владелец: всё из менеджерской карточки плюс ``lesson_price``.
Эндпоинты, которые их отдают, появятся в T2.02–T2.04; контракт приватности проверяется тестом
``tests/unit/test_privacy_contract.py`` и на самих схемах, и на всех эндпоинтах ``/student/*``
и ``/admin/*``.
"""

from typing import Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core import texts
from src.core.constants import (
    DEFAULT_USER_TIMEZONE,
    LIST_LIMIT_DEFAULT,
    PROFILE_URL_MAX_LENGTH,
)
from src.core.enums import UserRole
from src.schemas.auth import DISPLAY_NAME_MAX_LENGTH
from src.schemas.roles import audience_config

SCHOOL_CLASS_MIN = 1
SCHOOL_CLASS_MAX = 11
LESSON_PRICE_MAX = 1_000_000
TEACHER_NOTES_MAX_LENGTH = 5000


class StudentSelfProfile(BaseModel):
    """Профиль ученика для самого ученика (``/student/*``)."""

    model_config = audience_config(UserRole.STUDENT)

    user_id: int
    display_name: str
    timezone: str
    school_class: int | None
    video_url: str | None
    board_url: str | None
    subjects: list[str]


class StudentCardManager(BaseModel):
    """Карточка ученика для менеджера: без ``lesson_price`` и финансов."""

    model_config = audience_config(UserRole.MANAGER)

    user_id: int
    display_name: str
    timezone: str
    is_active: bool
    bot_blocked: bool
    telegram_linked: bool
    teacher_id: int
    school_class: int | None
    video_url: str | None
    board_url: str | None
    teacher_notes: str | None
    subjects: list[str]


class StudentCardOwner(StudentCardManager):
    """Карточка ученика для владельца: добавлена текущая цена занятия."""

    model_config = audience_config(UserRole.OWNER)

    lesson_price: int


# ------------------------------------------------------------------ запросы (вход)


def _https_url(value: str | None) -> str | None:
    """Ссылка профиля: только ``https://``; пустая строка означает «нет ссылки»."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    parts = urlsplit(stripped)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(texts.STUDENT_URL_NOT_HTTPS)
    return stripped


def _iana_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(texts.ME_TIMEZONE_UNKNOWN) from error
    return value


def _clean_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(texts.ME_NAME_BLANK)
    return stripped


class StudentCreate(BaseModel):
    """Создание профиля ученика (docs/08 §5.2).

    ``lesson_price`` может задать только владелец (проверяет сервис); ``teacher_id`` по умолчанию —
    сам создающий сотрудник.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    timezone: str = DEFAULT_USER_TIMEZONE
    school_class: int | None = Field(default=None, ge=SCHOOL_CLASS_MIN, le=SCHOOL_CLASS_MAX)
    subject_codes: list[str] = Field(default_factory=list, max_length=10)
    video_url: str | None = Field(default=None, max_length=PROFILE_URL_MAX_LENGTH)
    board_url: str | None = Field(default=None, max_length=PROFILE_URL_MAX_LENGTH)
    teacher_notes: str | None = Field(default=None, max_length=TEACHER_NOTES_MAX_LENGTH)
    lesson_price: int | None = Field(default=None, ge=0, le=LESSON_PRICE_MAX)
    teacher_id: int | None = None

    _name = field_validator("display_name")(_clean_name)
    _tz = field_validator("timezone")(_iana_timezone)
    _urls = field_validator("video_url", "board_url")(_https_url)


class StudentUpdate(BaseModel):
    """Частичное изменение профиля ученика: применяются только переданные поля.

    Явный ``null`` очищает необязательные поля (``school_class``, ссылки, заметки); для остальных
    ``null`` недопустим. Цену меняет только владелец (проверяет сервис).
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    timezone: str | None = None
    school_class: int | None = Field(default=None, ge=SCHOOL_CLASS_MIN, le=SCHOOL_CLASS_MAX)
    subject_codes: list[str] | None = Field(default=None, max_length=10)
    video_url: str | None = Field(default=None, max_length=PROFILE_URL_MAX_LENGTH)
    board_url: str | None = Field(default=None, max_length=PROFILE_URL_MAX_LENGTH)
    teacher_notes: str | None = Field(default=None, max_length=TEACHER_NOTES_MAX_LENGTH)
    lesson_price: int | None = Field(default=None, ge=0, le=LESSON_PRICE_MAX)
    teacher_id: int | None = None

    _urls = field_validator("video_url", "board_url")(_https_url)

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return None if value is None else _iana_timezone(value)

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(texts.STUDENT_UPDATE_EMPTY)
        not_nullable = (
            "display_name",
            "timezone",
            "subject_codes",
            "lesson_price",
            "teacher_id",
        )
        for name in not_nullable:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name}: {texts.STUDENT_FIELD_NOT_NULLABLE}")
        return self


# ------------------------------------------------------------------ список (ответ)


class StudentListItem(BaseModel):
    """Строка списка учеников для персонала: без цены и финансов."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    display_name: str
    school_class: int | None
    is_active: bool
    bot_blocked: bool
    telegram_linked: bool
    invite_pending: bool
    subjects: list[str]


class StudentListPage(BaseModel):
    """Страница списка учеников (docs/08 §1: ``items``, ``total``, ``limit``, ``offset``)."""

    items: list[StudentListItem]
    total: int
    limit: int = LIST_LIMIT_DEFAULT
    offset: int = 0
