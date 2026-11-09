"""Plan §2d: last/first complete week in account-local time (DST, zone ahead of and behind UTC)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfoNotFoundError

import pytest

from app.domain.weeks import first_complete_week, last_complete_week

SIX_ZONES = [
    "America/Chicago",
    "America/New_York",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "UTC",
]


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text)  # naive, holds UTC (like occurred_at)


@pytest.mark.parametrize(
    ("as_of", "tz", "expected"),
    [
        # L1: -6h -> Sun 02-08 23:59:59, Monday 02-02, -7 -> 01-26 (week 02-02 not complete yet)
        ("2026-02-09 05:59:59", "America/Chicago", date(2026, 1, 26)),
        # L2: -6h -> Mon 02-09 00:00:00, Monday 02-09, -7 -> 02-02
        ("2026-02-09 06:00:00", "America/Chicago", date(2026, 2, 2)),
        # L3: CDT -5 -> Sun 03-08 23:59:59, Monday 03-02, -7 -> 02-23
        ("2026-03-09 04:59:59", "America/Chicago", date(2026, 2, 23)),
        # L4: -5 -> Mon 03-09 00:00:00, Monday 03-09, -7 -> 03-02 (fixed -6 would give 02-23)
        ("2026-03-09 05:00:00", "America/Chicago", date(2026, 3, 2)),
        # L5: PDT -7 -> Sun 07-26 20:00 (UTC date is Mon 07-27), Monday 07-20, -7 -> 07-13
        ("2026-07-27 03:00:00", "America/Los_Angeles", date(2026, 7, 13)),
        # L6: +5:30 -> Mon 07-27 00:30 (UTC date is Sun 07-26), Monday 07-27, -7 -> 07-20
        ("2026-07-26 19:00:00", "Asia/Kolkata", date(2026, 7, 20)),
    ],
    ids=["L1", "L2", "L3", "L4", "L5", "L6"],
)
def test_last_complete_week(as_of: str, tz: str, expected: date) -> None:
    assert last_complete_week(utc(as_of), tz) == expected


@pytest.mark.parametrize("tz", SIX_ZONES)
def test_l7_seed_as_of_gives_2026_07_20_in_every_zone(tz: str) -> None:
    # local Mon 07-27 at Chicago 17:20:34, New York 18:20:34, Denver 16:20:34,
    # Los Angeles 15:20:34, Phoenix 15:20:34, UTC 22:20:34 -> Monday 07-27, -7
    assert last_complete_week(utc("2026-07-27 22:20:34"), tz) == date(2026, 7, 20)


def test_l8_aware_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        last_complete_week(datetime(2026, 7, 27, 22, 20, 34, tzinfo=UTC), "UTC")
    with pytest.raises(ValueError):
        first_complete_week(datetime(2026, 2, 1, 10, 57, 44, tzinfo=UTC), "UTC")


def test_l9_unknown_timezone_raises() -> None:
    with pytest.raises(ZoneInfoNotFoundError):
        last_complete_week(utc("2026-07-27 22:20:34"), "Mars/Olympus")


@pytest.mark.parametrize("tz", SIX_ZONES)
def test_f1_seed_data_start_gives_2026_02_02_in_every_zone(tz: str) -> None:
    # local Sun 02-01 at Chicago 04:57:44, NY 05:57:44, Denver 03:57:44, LA 02:57:44,
    # Phoenix 03:57:44, UTC 10:57:44 -> Monday 01-26, +7
    assert first_complete_week(utc("2026-02-01 10:57:44"), tz) == date(2026, 2, 2)


def test_f2_start_exactly_on_monday_midnight_keeps_that_week() -> None:
    assert first_complete_week(utc("2026-02-09 06:00:00"), "America/Chicago") == date(2026, 2, 9)


def test_f3_one_second_after_monday_midnight_skips_to_next_week() -> None:
    assert first_complete_week(utc("2026-02-09 06:00:01"), "America/Chicago") == date(2026, 2, 16)
