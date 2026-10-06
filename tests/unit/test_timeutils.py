"""Юнит-тесты модуля времени (задача T1.01).

Требования: `utcnow()` возвращает aware UTC; naive datetime запрещён
(`ValueError`); переводы между UTC и IANA-поясами корректны (docs/03 §1).
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from src.core.timeutils import ensure_aware, to_local, to_utc, utcnow


def test_utcnow_is_aware_utc() -> None:
    """utcnow() — aware datetime с tzinfo=timezone.utc."""
    now = utcnow()

    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)
    assert now.tzinfo == UTC


def test_to_utc_converts_moscow_to_utc() -> None:
    """Момент 12:00 Europe/Moscow (UTC+3, устойчиво — пояс без DST) → 09:00 UTC."""
    moscow_zone = ZoneInfo("Europe/Moscow")
    moscow_noon = datetime(2026, 10, 6, 12, 0, tzinfo=moscow_zone)
    result = to_utc(moscow_noon, "Europe/Moscow")

    assert result.tzinfo == UTC
    assert (result.year, result.month, result.day, result.hour, result.minute) == (
        2026,
        10,
        6,
        9,
        0,
    )


def test_to_utc_rejects_naive_datetime() -> None:
    """Naive datetime → ValueError (наивные значения запрещены проектом)."""
    with pytest.raises(ValueError):
        to_utc(datetime(2026, 10, 6, 12, 0), "Europe/Moscow")  # noqa: DTZ001


def test_to_local_converts_utc_to_moscow() -> None:
    """09:00 UTC → 12:00 Europe/Moscow (летом/зимом +3)."""
    utc_dt = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
    moscow = to_local(utc_dt, "Europe/Moscow")

    assert moscow.hour == 12
    assert str(moscow.tzinfo) == "Europe/Moscow"
    # Момент времени не изменился.
    assert moscow.astimezone(UTC) == utc_dt


def test_to_local_rejects_naive_datetime() -> None:
    """Naive datetime → ValueError."""
    with pytest.raises(ValueError):
        to_local(datetime(2026, 10, 6, 9, 0), "Europe/Moscow")  # noqa: DTZ001


def test_unknown_timezone_raises_value_error() -> None:
    """Неизвестное IANA-имя пояса → ValueError с понятным текстом."""
    utc_dt = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="Неизвестный часовой пояс"):
        to_local(utc_dt, "Mars/Olympus_Mons")


def test_ensure_aware_accepts_aware_and_rejects_naive() -> None:
    """ensure_aware пропускает aware и бросает ValueError на naive."""
    ensure_aware(datetime(2026, 10, 6, 9, 0, tzinfo=UTC))

    with pytest.raises(ValueError):
        ensure_aware(datetime(2026, 10, 6, 9, 0))  # noqa: DTZ001
