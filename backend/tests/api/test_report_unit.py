"""Pure helpers of the report service (plans/T3 §2a). No database."""

from datetime import date

import pytest

from app.errors import ApiError
from app.report import resolve_week, weeks_range


def test_u1_full_range_starts_eight_weeks_after_the_account_start() -> None:
    # first = 2026-02-02 + 8 * 7 days = 2026-03-30; 03-30 .. 07-20 is 112 days = 16 steps = 17 weeks
    weeks = weeks_range(date(2026, 2, 2), date(2026, 7, 20), 8)
    assert len(weeks) == 17
    assert weeks[0] == date(2026, 3, 30)
    assert weeks[-1] == date(2026, 7, 20)
    assert all(w.weekday() == 0 for w in weeks)
    assert all((b - a).days == 7 for a, b in zip(weeks, weeks[1:], strict=False))


def test_u2_account_starting_too_late_has_no_selectable_week() -> None:
    # first = 2026-07-13 + 56 days = 2026-09-07, after the last complete week
    assert weeks_range(date(2026, 7, 13), date(2026, 7, 20), 8) == []


def test_u3_small_history_gives_two_weeks() -> None:
    # first = 2026-02-02 + 14 days = 2026-02-16
    assert weeks_range(date(2026, 2, 2), date(2026, 2, 23), 2) == [
        date(2026, 2, 16),
        date(2026, 2, 23),
    ]


def test_u4_no_events_or_no_bounds_gives_no_week() -> None:
    assert weeks_range(None, date(2026, 7, 20), 8) == []
    assert weeks_range(date(2026, 2, 2), None, 8) == []


WEEKS = [date(2026, 2, 16), date(2026, 2, 23)]


def test_u5_resolve_week_none_gives_the_default() -> None:
    assert resolve_week(None, WEEKS) == date(2026, 2, 23)


def test_u5_resolve_week_none_without_weeks_gives_none() -> None:
    assert resolve_week(None, []) is None


def test_u5_resolve_week_listed_week_is_returned() -> None:
    assert resolve_week("2026-02-16", WEEKS) == date(2026, 2, 16)


@pytest.mark.parametrize(
    "week",
    [
        "2026-02-17",  # a Tuesday
        "2026-02-09",  # a Monday before the first selectable week
        "2026-03-02",  # a Monday after the last
    ],
)
def test_u5_resolve_week_rejects_weeks_outside_the_range(week: str) -> None:
    with pytest.raises(ApiError) as excinfo:
        resolve_week(week, WEEKS)
    assert excinfo.value.status == 422
    assert excinfo.value.code == "invalid_week"
    assert "2026-02-16 .. 2026-02-23" in excinfo.value.message


@pytest.mark.parametrize(
    "week", ["abc", "2026-13-01", "", "20260216", "2026-W08-1", "2026-2-16", " 2026-02-16"]
)
def test_u5_resolve_week_rejects_a_non_date(week: str) -> None:
    with pytest.raises(ApiError) as excinfo:
        resolve_week(week, WEEKS)
    assert (excinfo.value.status, excinfo.value.code) == (422, "invalid_week")


def test_u5_resolve_week_without_selectable_weeks_is_rejected() -> None:
    with pytest.raises(ApiError) as excinfo:
        resolve_week("2026-02-16", [])
    assert (excinfo.value.status, excinfo.value.code) == (422, "invalid_week")
    assert "no selectable weeks" in excinfo.value.message
