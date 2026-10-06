"""Работа с датой и временем (задача T1.01).

Правила проекта (`docs/03` §1, `docs/06` A4, QWEN.md §8):
- вся внутренняя логика живёт в UTC (`TIMESTAMPTZ`);
- наивные `datetime` запрещены: функции модуля бросают `ValueError`;
- `datetime.now()` вне этого модуля не используется (проверяется grep-шагом
  приёмки задачи и правилом Ruff DTZ);
- форматирование времени в поясе пользователя делает фронтенд — здесь только
  корректные переводы между UTC и IANA-поясами.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Минимальная длина SESSION_SECRET в байтах (требование задачи T1.01).
SECRET_MIN_BYTES = 32


def utcnow() -> datetime:
    """Вернуть текущий момент как aware-datetime в UTC.

    Единственное разрешённое место приложения, где берётся системное время
    (вместо устаревшего наивного `datetime.utcnow()`).

    Returns:
        Текущие дата и время с `tzinfo=timezone.utc`.
    """
    return datetime.now(UTC)


def ensure_aware(value: datetime) -> None:
    """Проверить, что `datetime` осведомлён о часовом поясе.

    Args:
        value: Проверяемое значение.

    Raises:
        ValueError: Если `value` наивный (без `tzinfo` или с пустым `utcoffset`).
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Ожидается aware datetime (с tzinfo); наивный datetime запрещён")


def _zone_or_error(tz_name: str) -> ZoneInfo:
    """Вернуть `ZoneInfo` по IANA-имени либо понятную ошибку.

    Args:
        tz_name: IANA-имя пояса, например `Europe/Moscow`.

    Returns:
        Объект зоны для перевода времени.

    Raises:
        ValueError: Имя пояса неизвестно системе (например, опечатка в БД).
    """
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"Неизвестный часовой пояс: {tz_name!r}") from error


def to_utc(local_dt: datetime, tz_name: str) -> datetime:
    """Перевести локальное время в UTC.

    Args:
        local_dt: Aware-дата и время (например, момент в поясе пользователя).
        tz_name: IANA-имя часового пояса, например `Europe/Moscow`.

    Returns:
        Aware-datetime в UTC.

    Raises:
        ValueError: Если `local_dt` наивный или пояс неизвестен системе.
    """
    ensure_aware(local_dt)
    _zone_or_error(tz_name)  # проверяем имя пояса до перевода
    return local_dt.astimezone(UTC)


def to_local(utc_dt: datetime, tz_name: str) -> datetime:
    """Перевести UTC-время (или любое aware-время) в указанный IANA-пояс.

    Args:
        utc_dt: Aware-datetime (обычно в UTC).
        tz_name: IANA-имя целевого пояса.

    Returns:
        Aware-datetime в поясе `tz_name`.

    Raises:
        ValueError: Если `utc_dt` наивный или пояс неизвестен.
    """
    ensure_aware(utc_dt)
    zone = _zone_or_error(tz_name)
    return utc_dt.astimezone(zone)
