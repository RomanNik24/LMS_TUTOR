"""Тесты помощников расписания в ``timeutils`` (T3.03): пояса, DST, границы суток."""

from datetime import UTC, date, datetime, time

import pytest
from src.core.timeutils import (
    dates_on_weekday,
    day_bounds_utc,
    local_date_of,
    local_to_utc,
    weekly_starts_utc,
)

BERLIN = "Europe/Berlin"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# ---------------------------------------------------------------- local_to_utc


def test_timeutils_moscow_is_plus_3_all_year() -> None:
    assert local_to_utc(date(2026, 1, 15), time(17, 0), "Europe/Moscow") == utc(2026, 1, 15, 14, 0)
    assert local_to_utc(date(2026, 7, 15), time(17, 0), "Europe/Moscow") == utc(2026, 7, 15, 14, 0)


def test_timeutils_kaliningrad_is_plus_2() -> None:
    assert local_to_utc(date(2026, 10, 7), time(9, 30), "Europe/Kaliningrad") == utc(
        2026, 10, 7, 7, 30
    )


def test_timeutils_yekaterinburg_is_plus_5() -> None:
    assert local_to_utc(date(2026, 10, 7), time(20, 0), "Asia/Yekaterinburg") == utc(
        2026, 10, 7, 15, 0
    )


def test_timeutils_berlin_winter_and_summer_offsets() -> None:
    assert local_to_utc(date(2026, 1, 15), time(17, 0), BERLIN) == utc(2026, 1, 15, 16, 0)
    assert local_to_utc(date(2026, 7, 15), time(17, 0), BERLIN) == utc(2026, 7, 15, 15, 0)


def test_timeutils_local_date_may_differ_from_utc_date() -> None:
    """23:30 в Екатеринбурге — ещё предыдущая дата по UTC."""
    moment = local_to_utc(date(2026, 10, 7), time(1, 30), "Asia/Yekaterinburg")
    assert moment == utc(2026, 10, 6, 20, 30)
    assert local_date_of(moment, "Asia/Yekaterinburg") == date(2026, 10, 7)


def test_timeutils_dst_gap_time_moves_forward() -> None:
    """2026-03-29 02:30 в Берлине не существует (02:00→03:00): считается как 03:30 местного."""
    assert local_to_utc(date(2026, 3, 29), time(2, 30), BERLIN) == utc(2026, 3, 29, 1, 30)


def test_timeutils_dst_ambiguous_time_takes_first_occurrence() -> None:
    """2026-10-25 02:30 в Берлине бывает дважды; берём первое (летнее, UTC+2)."""
    assert local_to_utc(date(2026, 10, 25), time(2, 30), BERLIN) == utc(2026, 10, 25, 0, 30)


def test_timeutils_rejects_unknown_zone_and_aware_time() -> None:
    with pytest.raises(ValueError, match="Неизвестный часовой пояс"):
        local_to_utc(date(2026, 1, 1), time(10, 0), "Mars/Base")
    with pytest.raises(ValueError, match="без tzinfo"):
        local_to_utc(date(2026, 1, 1), time(10, 0, tzinfo=UTC), "Europe/Moscow")


# ---------------------------------------------------------------- границы суток


def test_timeutils_day_bounds_regular_day_is_24_hours() -> None:
    start, end = day_bounds_utc(date(2026, 10, 7), "Europe/Moscow")
    assert start == utc(2026, 10, 6, 21, 0)
    assert end - start == (utc(2026, 10, 7, 21, 0) - utc(2026, 10, 6, 21, 0))


def test_timeutils_day_bounds_spring_forward_is_23_hours() -> None:
    start, end = day_bounds_utc(date(2026, 3, 29), BERLIN)
    assert (end - start).total_seconds() == 23 * 3600


def test_timeutils_day_bounds_fall_back_is_25_hours() -> None:
    start, end = day_bounds_utc(date(2026, 10, 25), BERLIN)
    assert (end - start).total_seconds() == 25 * 3600


def test_timeutils_day_bounds_leap_day() -> None:
    """29 февраля 2028 (високосный год) существует и длится 24 часа."""
    start, end = day_bounds_utc(date(2028, 2, 29), "Europe/Moscow")
    assert start == utc(2028, 2, 28, 21, 0)
    assert end == utc(2028, 2, 29, 21, 0)


def test_timeutils_day_bounds_year_end() -> None:
    start, end = day_bounds_utc(date(2026, 12, 31), "Europe/Moscow")
    assert end == utc(2026, 12, 31, 21, 0)
    assert start == utc(2026, 12, 30, 21, 0)


# ---------------------------------------------------------------- дни недели


def test_timeutils_dates_on_weekday_basic() -> None:
    """Вторники с 1 по 31 октября 2026 (1 октября — четверг)."""
    assert dates_on_weekday(date(2026, 10, 1), date(2026, 10, 31), 2) == [
        date(2026, 10, 6),
        date(2026, 10, 13),
        date(2026, 10, 20),
        date(2026, 10, 27),
    ]


def test_timeutils_dates_on_weekday_bounds_are_inclusive() -> None:
    assert dates_on_weekday(date(2026, 10, 6), date(2026, 10, 13), 2) == [
        date(2026, 10, 6),
        date(2026, 10, 13),
    ]


def test_timeutils_dates_on_weekday_empty_and_invalid() -> None:
    assert dates_on_weekday(date(2026, 10, 7), date(2026, 10, 1), 1) == []
    assert dates_on_weekday(date(2026, 10, 7), date(2026, 10, 9), 7) == []
    for bad in (0, 8):
        with pytest.raises(ValueError, match="1..7"):
            dates_on_weekday(date(2026, 10, 1), date(2026, 10, 31), bad)


def test_timeutils_dates_on_weekday_sunday_is_7() -> None:
    assert dates_on_weekday(date(2026, 10, 1), date(2026, 10, 12), 7) == [
        date(2026, 10, 4),
        date(2026, 10, 11),
    ]


def test_timeutils_dates_on_weekday_across_leap_day() -> None:
    assert date(2028, 2, 29) in dates_on_weekday(date(2028, 2, 1), date(2028, 3, 31), 2)


# ---------------------------------------------------------------- серия уроков и DST


def test_timeutils_weekly_series_keeps_local_time_across_dst() -> None:
    """Воскресенья 17:00 в Берлине через переход 25 октября: час на часах тот же, UTC +1 ч."""
    starts = weekly_starts_utc(7, time(17, 0), BERLIN, date(2026, 10, 18), date(2026, 11, 1))
    assert starts == [utc(2026, 10, 18, 15, 0), utc(2026, 10, 25, 16, 0), utc(2026, 11, 1, 16, 0)]


def test_timeutils_weekly_series_in_moscow_has_constant_utc_time() -> None:
    starts = weekly_starts_utc(2, time(17, 0), "Europe/Moscow", date(2026, 3, 1), date(2026, 11, 1))
    assert {s.time() for s in starts} == {time(14, 0)}
    assert len(starts) == 35


def test_timeutils_weekly_series_is_idempotent_and_sorted() -> None:
    args = (5, time(10, 0), "Asia/Yekaterinburg", date(2026, 10, 1), date(2026, 12, 31))
    first = weekly_starts_utc(*args)
    assert first == weekly_starts_utc(*args)
    assert first == sorted(first)
