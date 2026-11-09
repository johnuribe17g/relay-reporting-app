"""Zero-filled weekly series over clean_events (plans/T2-backend-core.md §2e, SQ1-SQ15).

Accounts: 1 Chicago (CST -6 in February), 2 Denver (MST -7), 3 Chicago with no events.
Mondays: 02-02, 02-09, 02-16, 02-23. Unless stated: first_week = 2026-02-02, lookback = 12,
selected week W = 2026-02-09. Each test runs inside the rolled-back `conn` transaction.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import Connection, text

from app.domain.models import Series
from app.series import AccountSeries, fetch_bounds, fetch_series, history_and_x

FIRST = date(2026, 2, 2)
W0202, W0209, W0216, W0223 = (
    date(2026, 2, 2),
    date(2026, 2, 9),
    date(2026, 2, 16),
    date(2026, 2, 23),
)


class Db:
    """The test connection plus a tiny event inserter with auto ids."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.next_id = 1
        for account_id, tz in {
            1: "America/Chicago",
            2: "America/Denver",
            3: "America/Chicago",
        }.items():
            conn.execute(
                text("INSERT INTO accounts VALUES (:id, :n, 'Test', :tz, '2025-01-01 00:00:00')"),
                {"id": account_id, "n": f"A{account_id}", "tz": tz},
            )

    def add(
        self,
        at: str,
        *,
        account: int = 1,
        location: str = "Site A",
        event_type: str = "call_received",
        event_id: int | None = None,
    ) -> None:
        if event_id is None:
            event_id = self.next_id
            self.next_id += 1
        self.conn.execute(
            text("INSERT INTO activity_events VALUES (:id, :a, :l, :t, :at, NULL, NULL)"),
            {
                "id": event_id,
                "a": account,
                "l": location,
                "t": event_type,
                "at": datetime.fromisoformat(at),
            },
        )

    def series(
        self,
        week: date = W0209,
        *,
        account: int = 1,
        first: date = FIRST,
        lookback: int = 12,
    ) -> AccountSeries:
        return fetch_series(self.conn, account, week, first, lookback)


@pytest.fixture
def db(conn: Connection) -> Db:
    return Db(conn)


def loc(result: AccountSeries, name: str) -> Series:
    matches = [s for s in result.locations if s.key == name]
    assert len(matches) == 1, f"{name!r} not in {[s.key for s in result.locations]}"
    return matches[0]


def totals(series: Series) -> list[int]:
    return [w.total for w in series.weeks]


def weeks_of(series: Series) -> list[date]:
    return [w.week for w in series.weeks]


def test_sq1_zero_fill_keeps_a_silent_week(db: Db) -> None:
    db.add("2026-02-03 15:00:00")  # Chicago Tue 09:00 -> week 02-02
    db.add("2026-02-04 15:00:00")  # week 02-02
    db.add("2026-02-18 15:00:00")  # week 02-16
    site_a = loc(db.series(W0223), "Site A")
    assert weeks_of(site_a) == [W0202, W0209, W0216, W0223]
    assert totals(site_a) == [2, 0, 1, 0]
    assert history_and_x(site_a) == ([2, 0, 1], 0)


def test_sq2_location_starting_mid_series_and_future_guard(db: Db) -> None:
    db.add("2026-02-03 15:00:00")  # Site A, week 02-02
    db.add("2026-02-17 10:00:00", location="Site B")  # Chicago Tue 04:00 -> week 02-16
    site_b = loc(db.series(W0223), "Site B")
    assert weeks_of(site_b) == [W0216, W0223]
    assert totals(site_b) == [1, 0]
    # at W = 02-09 Site B starts in the future: absent, not listed
    early = db.series(W0209)
    assert [s.key for s in early.locations] == ["Site A"]


def test_sq3_event_in_partial_first_week_is_outside_the_grid(db: Db) -> None:
    db.add("2026-02-01 16:00:00", location="Site C")  # Chicago Sun 10:00 -> week 01-26
    db.add("2026-02-03 15:00:00", location="Site C")  # week 02-02
    site_c = loc(db.series(W0209), "Site C")
    assert site_c.start_week == W0202
    assert weeks_of(site_c) == [W0202, W0209]
    assert totals(site_c) == [1, 0]


def test_sq3b_location_with_only_a_partial_week_event_exists_from_first_week(db: Db) -> None:
    db.add("2026-02-01 16:00:00", location="Site D")
    site_d = loc(db.series(W0209), "Site D")
    assert site_d.start_week == W0202
    assert weeks_of(site_d) == [W0202, W0209]
    assert totals(site_d) == [0, 0]


def test_sq4_by_type_normalizes_and_counts_unknown_separately(db: Db) -> None:
    db.add("2026-02-03 15:00:00", event_type="call_received")
    db.add("2026-02-03 15:01:00", event_type="call_received")
    db.add("2026-02-03 15:02:00", event_type="lead_created")
    db.add("2026-02-03 15:03:00", event_type="appointment_set")
    db.add("2026-02-03 15:04:00", event_type="phone_call")
    db.add("2026-02-03 15:05:00", event_type=" Call_Received ")  # the view normalizes it
    week = loc(db.series(W0209), "Site A").weeks[0]
    assert week.week == W0202
    assert (week.call_received, week.lead_created, week.appointment_set, week.unknown) == (
        3,
        1,
        1,
        1,
    )
    assert week.total == 5  # unknown excluded


def test_sq5_account_series_is_the_sum_of_locations(db: Db) -> None:
    db.add("2026-02-03 15:00:00")
    db.add("2026-02-04 15:00:00")
    db.add("2026-02-18 15:00:00")  # Site A: [2, 0, 1, 0]
    db.add("2026-02-17 10:00:00", location="Site B")  # Site B: week 02-16 -> 1, 02-23 -> 0
    result = db.series(W0223)
    assert result.account is not None
    assert result.account.key is None
    assert result.account.start_week == W0202
    assert weeks_of(result.account) == [W0202, W0209, W0216, W0223]
    assert totals(result.account) == [2, 0, 2, 0]


def test_sq6_buckets_on_local_week(db: Db) -> None:
    db.add("2026-02-09 05:59:59")  # Chicago Sun 23:59:59 -> week 02-02
    db.add("2026-02-09 06:00:00")  # Chicago Mon 00:00:00 -> week 02-09
    assert totals(loc(db.series(W0209), "Site A")) == [1, 1]


def test_sq7_other_accounts_never_leak_in(db: Db) -> None:
    db.add("2026-02-03 15:00:00")  # A1 Site A, week 02-02
    db.add(
        "2026-02-03 15:00:00", account=2
    )  # A2 Denver Tue 08:00 -> week 02-02, same location name
    db.add("2026-02-03 15:01:00", account=2)
    a1, a2 = db.series(account=1), db.series(account=2)
    assert totals(loc(a1, "Site A")) == [1, 0]
    assert a1.account is not None and totals(a1.account) == [1, 0]
    assert a2.account is not None and totals(a2.account) == [2, 0]


def test_sq8_account_without_events(db: Db) -> None:
    result = db.series(account=3)
    assert result.has_events is False
    assert result.account is None
    assert result.locations == ()


def test_sq13_account_that_starts_after_the_week(db: Db) -> None:
    db.add("2026-02-24 15:00:00")  # week 02-23
    result = db.series(W0209)
    assert result.has_events is True
    assert result.account is None
    assert result.locations == ()


def test_sq14_bounds(db: Db) -> None:
    assert fetch_bounds(db.conn) == (None, None)
    db.add("2026-07-27 22:20:34")
    db.add("2026-02-01 10:57:44")
    assert fetch_bounds(db.conn) == (
        datetime(2026, 2, 1, 10, 57, 44),
        datetime(2026, 7, 27, 22, 20, 34),
    )


def test_sq9_exact_duplicate_counts_once(db: Db) -> None:
    db.add("2026-02-03 15:00:00", event_id=1)
    db.add("2026-02-03 15:00:00", event_id=2)
    assert totals(loc(db.series(W0209), "Site A")) == [1, 0]


def test_sq10_lookback_clips_the_grid_but_not_the_start(db: Db) -> None:
    # one event every Tuesday 15:00 UTC for the 16 weeks 02-02 .. 05-18
    for k in range(16):
        day = date(2026, 2, 3).toordinal() + 7 * k
        db.add(f"{date.fromordinal(day).isoformat()} 15:00:00")
    site_a = loc(db.series(date(2026, 5, 18), lookback=12), "Site A")
    assert len(site_a.weeks) == 13
    assert site_a.weeks[0].week == date(2026, 2, 23)  # W - 84 days
    assert site_a.weeks[-1].week == date(2026, 5, 18)
    assert totals(site_a) == [1] * 13
    assert site_a.start_week == W0202


def test_sq11_events_after_the_week_are_ignored(db: Db) -> None:
    db.add("2026-02-03 15:00:00")  # Site A, week 02-02
    db.add("2026-02-24 15:00:00")  # Site A, week 02-23 (after W)
    db.add("2026-02-24 15:00:00", location="Site F")  # only after W
    result = db.series(W0216)
    assert [s.key for s in result.locations] == ["Site A"]
    assert weeks_of(loc(result, "Site A")) == [W0202, W0209, W0216]
    assert totals(loc(result, "Site A")) == [1, 0, 0]


def test_sq12_unknown_only_location_exists_with_zero_total(db: Db) -> None:
    db.add("2026-02-03 15:00:00", location="Site E", event_type="phone_call")
    site_e = loc(db.series(W0209), "Site E")
    assert totals(site_e) == [0, 0]
    assert [w.unknown for w in site_e.weeks] == [1, 0]


@pytest.mark.parametrize(
    ("week", "first"),
    [(date(2026, 2, 4), FIRST), (W0209, date(2026, 2, 3))],
    ids=["week-not-monday", "first-week-not-monday"],
)
def test_sq15_non_monday_arguments_are_rejected(db: Db, week: date, first: date) -> None:
    with pytest.raises(ValueError):
        db.series(week, first=first)
