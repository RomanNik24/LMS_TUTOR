"""Общие помощники хэндлеров бота."""

from src.core import texts
from src.core.enums import UserRole


def greeting_for(role: UserRole, display_name: str) -> str:
    """Приветствие по роли: ученику «ты», персоналу нейтрально (ADR 0001)."""
    if role == UserRole.STUDENT:
        return texts.BOT_STUDENT_GREETING.format(name=display_name)
    return texts.BOT_STAFF_GREETING.format(name=display_name)
