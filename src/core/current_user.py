"""Текущий пользователь для сервисного слоя (задача T1.06).

Все методы сервисов принимают ``actor: CurrentUser`` первым аргументом
(docs/08 §9). Это неизменяемый снимок данных, нужных для проверки прав;
ORM-модель ``User`` в сервисы как «актора» не передаётся.
"""

from dataclasses import dataclass

from src.core.enums import UserRole


@dataclass(frozen=True)
class CurrentUser:
    """Снимок авторизованного пользователя.

    Attributes:
        id: Идентификатор пользователя (``users.id``).
        role: Роль пользователя (docs/09 §3).
        timezone: IANA-часовой пояс пользователя.
    """

    id: int
    role: UserRole
    timezone: str
