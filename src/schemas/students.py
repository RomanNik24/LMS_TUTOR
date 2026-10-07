"""Схемы карточки ученика по ролям (docs/04 §2.2, docs/08 §8, T2.01).

Три отдельные схемы вместо одной со скрытием полей:
- ``StudentSelfProfile`` — ученик о себе: без цены, заметок и финансов;
- ``StudentCardManager`` — менеджер: заметки преподавателя есть, цены и финансов нет;
- ``StudentCardOwner`` — владелец: всё из менеджерской карточки плюс ``lesson_price``.
Эндпоинты, которые их отдают, появятся в T2.02–T2.04; контракт приватности проверяется тестом
``tests/unit/test_privacy_contract.py`` и на самих схемах, и на всех эндпоинтах ``/student/*``
и ``/admin/*``.
"""

from pydantic import BaseModel

from src.core.enums import UserRole
from src.schemas.roles import audience_config


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
