"""Seed load and the numbers in docs/data-profile.md (plans/T1-scaffold-db.md §6d).

The seed is loaded once per module inside a transaction that is rolled back at the end. All
tests share that one connection, so the idempotence and atomicity tests use SAVEPOINTs instead
of a second connection (which would block on the TRUNCATE lock).

Counts here are for `clean_events` (after the 12 exact duplicates are removed) unless marked raw.
The profile quotes raw counts, e.g. 881 for account 6's spike week; the view gives 880.
"""

import statistics
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from app.seed import load_seed

KNOWN_EVENT_TYPES = {"call_received", "lead_created", "appointment_set"}


@pytest.fixture(scope="module")
def seeded(test_engine: Engine) -> Iterator[Connection]:
    with test_engine.connect() as connection:
        connection.begin()
        load_seed(connection)
        yield connection
        connection.rollback()


def scalar(conn: Connection, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar_one())


def counts(conn: Connection) -> tuple[int, int, int]:
    return (
        scalar(conn, "SELECT count(*) FROM accounts"),
        scalar(conn, "SELECT count(*) FROM activity_events"),
        scalar(conn, "SELECT count(*) FROM clean_events"),
    )


def test_raw_counts(seeded: Connection) -> None:
    assert scalar(seeded, "SELECT count(*) FROM accounts") == 20
    assert scalar(seeded, "SELECT count(*) FROM activity_events") == 12_626


def test_clean_events_removes_exactly_twelve(seeded: Connection) -> None:
    assert scalar(seeded, "SELECT count(*) FROM clean_events") == 12_614


# (kept id, removed id): the 12 exact duplicate pairs, consecutive ids (profile §7).
DUPLICATE_PAIRS = [
    (1523, 1524),
    (1538, 1539),
    (2236, 2237),
    (5851, 5852),
    (5856, 5857),
    (6325, 6326),
    (6966, 6967),
    (7524, 7525),
    (8738, 8739),
    (9595, 9596),
    (9603, 9604),
    (11266, 11267),
]


def test_the_twelve_removed_ids(seeded: Connection) -> None:
    present = {r[0] for r in seeded.execute(text("SELECT id FROM clean_events"))}
    for kept, removed in DUPLICATE_PAIRS:
        assert kept in present, f"lowest id {kept} must be kept"
        assert removed not in present, f"duplicate id {removed} must be removed"


def test_removed_rows_per_account(seeded: Connection) -> None:
    rows = seeded.execute(
        text(
            """
            SELECT a.id,
                   (SELECT count(*) FROM activity_events e WHERE e.account_id = a.id)
                 - (SELECT count(*) FROM clean_events c WHERE c.account_id = a.id) AS removed
            FROM accounts a ORDER BY a.id
            """
        )
    )
    assert {r[0]: r[1] for r in rows if r[1]} == {6: 4, 1: 2, 18: 2, 2: 1, 4: 1, 8: 1, 12: 1}


def test_clean_counts_by_event_type(seeded: Connection) -> None:
    # Raw 7,780 / 3,044 / 1,802 minus the dedupe (9 / 2 / 1 = 12).
    rows = seeded.execute(text("SELECT event_type, count(*) FROM clean_events GROUP BY event_type"))
    assert {r[0]: r[1] for r in rows} == {
        "call_received": 7_771,
        "lead_created": 3_042,
        "appointment_set": 1_801,
    }


def test_account_20_has_no_events(seeded: Connection) -> None:
    assert scalar(seeded, "SELECT count(*) FROM clean_events WHERE account_id = 20") == 0


def test_sixty_nine_locations(seeded: Connection) -> None:
    assert (
        scalar(
            seeded,
            "SELECT count(*) FROM (SELECT DISTINCT account_id, location FROM clean_events) x",
        )
        == 69
    )


def test_weeks_and_partial_boundary_weeks(seeded: Connection) -> None:
    assert scalar(seeded, "SELECT count(DISTINCT local_week) FROM clean_events") == 27
    assert (
        scalar(
            seeded,
            "SELECT count(DISTINCT local_week) FROM clean_events "
            "WHERE local_week BETWEEN '2026-02-02' AND '2026-07-20'",
        )
        == 25
    )
    for week, events, accounts in (("2026-01-26", 18, 8), ("2026-07-27", 79, 17)):
        row = seeded.execute(
            text(
                "SELECT count(*), count(DISTINCT account_id) FROM clean_events "
                "WHERE local_week = :w"
            ),
            {"w": date.fromisoformat(week)},
        ).one()
        assert tuple(row) == (events, accounts), f"partial week {week}"


def account_6_weekly_totals(conn: Connection) -> dict[date, int]:
    rows = conn.execute(
        text("SELECT local_week, count(*) FROM clean_events WHERE account_id = 6 GROUP BY 1")
    )
    return {r[0]: r[1] for r in rows}


def test_account_6_spike_week(seeded: Connection) -> None:
    totals = account_6_weekly_totals(seeded)
    # Profile §11 says 881: that is the raw count. Ids 8738/8739 are an account 6 duplicate pair
    # inside the spike week, so the cleaned figure is 880.
    assert totals[date(2026, 6, 1)] == 880
    assert totals[date(2026, 6, 8)] == 102
    complete = [date(2026, 2, 2) + timedelta(weeks=i) for i in range(25)]
    assert complete[-1] == date(2026, 7, 20)
    assert statistics.median(totals.get(w, 0) for w in complete) == 76
    # Dataset-wide the same week is 1,269 cleaned (1,270 raw).
    assert (
        scalar(seeded, "SELECT count(*) FROM clean_events WHERE local_week = '2026-06-01'") == 1269
    )


# id: (timezone, UTC occurred_at, local_ts, local_week, UTC week). local = UTC + offset:
# Denver MST -7 (winter) / MDT -6 (summer), Los Angeles PST -8 / PDT -7,
# Chicago CST -6 (before 2026-03-08) / CDT -5, New York EDT -4.
WEEK_CHANGERS = {
    476: (
        "America/Denver",
        "2026-02-09 06:02:46",
        "2026-02-08 23:02:46",
        "2026-02-02",
        "2026-02-09",
    ),
    932: (
        "America/Los_Angeles",
        "2026-02-16 04:01:23",
        "2026-02-15 20:01:23",
        "2026-02-09",
        "2026-02-16",
    ),
    1871: (
        "America/Chicago",
        "2026-03-02 05:11:21",
        "2026-03-01 23:11:21",
        "2026-02-23",
        "2026-03-02",
    ),
    10146: (
        "America/Los_Angeles",
        "2026-06-22 06:36:23",
        "2026-06-21 23:36:23",
        "2026-06-15",
        "2026-06-22",
    ),
    11092: (
        "America/New_York",
        "2026-07-06 02:39:28",
        "2026-07-05 22:39:28",
        "2026-06-29",
        "2026-07-06",
    ),
    11093: (
        "America/Denver",
        "2026-07-06 02:40:24",
        "2026-07-05 20:40:24",
        "2026-06-29",
        "2026-07-06",
    ),
    11094: (
        "America/Chicago",
        "2026-07-06 03:35:05",
        "2026-07-05 22:35:05",
        "2026-06-29",
        "2026-07-06",
    ),
    12045: (
        "America/Denver",
        "2026-07-20 05:15:54",
        "2026-07-19 23:15:54",
        "2026-07-13",
        "2026-07-20",
    ),
}


def test_events_that_change_week_between_local_and_utc(seeded: Connection) -> None:
    rows = seeded.execute(
        text(
            """
            SELECT c.id, a.timezone, c.occurred_at, c.local_ts, c.local_week,
                   date_trunc('week', c.occurred_at)::date AS utc_week
            FROM clean_events c JOIN accounts a ON a.id = c.account_id
            WHERE c.local_week <> date_trunc('week', c.occurred_at)::date
            """
        )
    ).all()
    actual = {r.id: (r.timezone, r.occurred_at, r.local_ts, r.local_week, r.utc_week) for r in rows}
    expected = {
        event_id: (
            tz,
            datetime.fromisoformat(utc),
            datetime.fromisoformat(local),
            date.fromisoformat(week),
            date.fromisoformat(utc_week),
        )
        for event_id, (tz, utc, local, week, utc_week) in WEEK_CHANGERS.items()
    }
    assert actual == expected
    by_zone: dict[str, int] = {}
    for tz, *_ in actual.values():
        by_zone[tz] = by_zone.get(tz, 0) + 1
    # Phoenix and UTC contribute none.
    assert by_zone == {
        "America/Chicago": 2,
        "America/Denver": 3,
        "America/Los_Angeles": 2,
        "America/New_York": 1,
    }


def test_data_quality_no_unknown_event_types(seeded: Connection) -> None:
    """The view does not filter event_type, so unknown values would show up here (PLAN §3)."""
    found = {r[0] for r in seeded.execute(text("SELECT DISTINCT event_type FROM clean_events"))}
    unknown = found - KNOWN_EVENT_TYPES
    assert not unknown, f"unknown event_type values in the data: {sorted(unknown)}"


def test_account_timezones_are_valid_iana_names(seeded: Connection) -> None:
    zones = {r[0] for r in seeded.execute(text("SELECT DISTINCT timezone FROM accounts"))}
    valid = {r[0] for r in seeded.execute(text("SELECT name FROM pg_timezone_names"))}
    assert zones <= valid
    assert zones == {
        "America/Chicago",
        "America/New_York",
        "America/Denver",
        "America/Los_Angeles",
        "America/Phoenix",
        "UTC",
    }


def test_load_seed_is_idempotent(seeded: Connection) -> None:
    before = counts(seeded)
    assert before == (20, 12_626, 12_614)
    with seeded.begin_nested():  # SAVEPOINT, released on exit
        load_seed(seeded)
        assert counts(seeded) == before
    assert counts(seeded) == before


def test_failed_load_leaves_previous_load_intact(seeded: Connection, tmp_path: Path) -> None:
    """TRUNCATE succeeds, then a statement fails. Rolling back the SAVEPOINT must undo the
    TRUNCATE. (A SAVEPOINT is needed: an error aborts the whole outer transaction in Postgres.)
    """
    broken = tmp_path / "broken.sql"
    broken.write_text("INSERT INTO table_that_does_not_exist VALUES (1);\n")
    before = counts(seeded)
    savepoint = seeded.begin_nested()
    with pytest.raises(DBAPIError):
        load_seed(seeded, broken)
    savepoint.rollback()
    assert counts(seeded) == before
