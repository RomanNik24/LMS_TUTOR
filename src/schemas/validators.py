"""Общие валидаторы полей схем (имя, часовой пояс, ссылки https)."""

from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core import texts


def https_url(value: str | None) -> str | None:
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


def iana_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(texts.ME_TIMEZONE_UNKNOWN) from error
    return value


def clean_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(texts.ME_NAME_BLANK)
    return stripped
