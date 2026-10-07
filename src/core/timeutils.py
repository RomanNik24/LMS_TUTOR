"""Работа с датой и временем (задача T1.01).

Правила проекта (`docs/03` §1, `docs/06` A4, QWEN.md §8):
- вся внутренняя логика живёт в UTC (`TIMESTAMPTZ`);
- наивные `datetime` запрещены: функции модуля бросают `ValueError`;
- `datetime.now()` вне этого модуля не используется (проверяется grep-шагом
  приёмки задачи и правилом Ruff DTZ);
- форматирование времени в поясе пользователя делает фронтенд — здесь только
  корректные переводы между UTC и IANA-поясами.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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


ISO_WEEKDAY_MIN = 1
ISO_WEEKDAY_MAX = 7
DAYS_IN_WEEK = 7


def local_to_utc(day: date, at: time, tz_name: str) -> datetime:
    """Перевести «дата + локальное время стены» в UTC (docs/03 §1, T3.03).

    Правила переходов на летнее/зимнее время (используется ``zoneinfo``):
    - несуществующее время (час «пропал» при переходе вперёд) сдвигается вперёд на длину
      пропуска: 02:30 при переходе 02:00 → 03:00 становится 03:30 местного;
    - неоднозначное время (час повторяется при переходе назад) — первое вхождение.

    Args:
        day: Календарная дата в поясе ``tz_name``.
        at: Время на часах (naive ``time``; пояс задаётся ``tz_name``).
        tz_name: IANA-имя пояса.

    Returns:
        Aware-datetime в UTC.

    Raises:
        ValueError: Неизвестный пояс или ``at`` с ``tzinfo``.
    """
    if at.tzinfo is not None:
        raise ValueError("Локальное время шаблона должно быть без tzinfo")
    zone = _zone_or_error(tz_name)
    return datetime.combine(day, at, tzinfo=zone).astimezone(UTC)


def local_date_of(moment: datetime, tz_name: str) -> date:
    """Календарная дата момента в поясе ``tz_name`` (для «сегодня» пользователя)."""
    return to_local(moment, tz_name).date()


def day_bounds_utc(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """Границы местных суток в UTC: полуинтервал ``[начало, конец)``.

    Сутки с переходом на DST длятся 23 или 25 часов; конец считается как местная полночь
    следующих суток, а не «+24 часа».

    Args:
        day: Календарная дата в поясе ``tz_name``.
        tz_name: IANA-имя пояса.

    Returns:
        Пара aware-datetime в UTC: (начало, конец).
    """
    midnight = time(0, 0)
    return (
        local_to_utc(day, midnight, tz_name),
        local_to_utc(day + timedelta(days=1), midnight, tz_name),
    )


def dates_on_weekday(first: date, last: date, iso_weekday: int) -> list[date]:
    """Все даты от ``first`` до ``last`` включительно, выпадающие на день недели ISO.

    Args:
        first: Первая дата диапазона.
        last: Последняя дата диапазона (включительно).
        iso_weekday: 1 = понедельник … 7 = воскресенье.

    Returns:
        Даты по возрастанию; пусто, если ``last < first``.

    Raises:
        ValueError: ``iso_weekday`` вне 1..7.
    """
    if not ISO_WEEKDAY_MIN <= iso_weekday <= ISO_WEEKDAY_MAX:
        raise ValueError(f"День недели ISO должен быть 1..7, получено {iso_weekday}")
    if last < first:
        return []
    shift = (iso_weekday - first.isoweekday()) % DAYS_IN_WEEK
    current = first + timedelta(days=shift)
    result: list[date] = []
    while current <= last:
        result.append(current)
        current += timedelta(days=DAYS_IN_WEEK)
    return result


def weekly_starts_utc(
    iso_weekday: int, start_local_time: time, tz_name: str, first: date, last: date
) -> list[datetime]:
    """Моменты начала еженедельных уроков в UTC за ``[first, last]`` (генерация шаблона).

    Локальное время урока НЕ сдвигается при смене DST: 17:00 в Берлине остаётся 17:00 на часах,
    а UTC-момент меняется на час.

    Args:
        iso_weekday: День недели ISO (1..7).
        start_local_time: Время на часах в поясе шаблона.
        tz_name: IANA-пояс шаблона.
        first: С какой даты (включительно, дата в поясе шаблона).
        last: По какую дату (включительно).

    Returns:
        Aware-datetime в UTC по возрастанию.
    """
    return [
        local_to_utc(day, start_local_time, tz_name)
        for day in dates_on_weekday(first, last, iso_weekday)
    ]
