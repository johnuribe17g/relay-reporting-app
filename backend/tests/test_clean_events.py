"""clean_events view: dedupe, normalization, timezone direction, week edges, DST.

Fixtures are tiny and hand-computed (plans/T1-scaffold-db.md §6a/§6b). Every timestamp case
shows the UTC -> local arithmetic. local = UTC + offset; local_week = the Monday on or before
the local date. 2026-02-01 is a Sunday; US DST began 2026-03-08 02:00 local
(08:00 UTC in Chicago, 09:00 UTC in Denver).
"""

from datetime import date, datetime

import pytest
from sqlalchemy import Connection, text

ACCOUNTS = {
    1: "America/Chicago",
    2: "America/Denver",
    3: "America/Phoenix",
    4: "UTC",
    5: "Asia/Kolkata",
    6: "America/New_York",
}


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


@pytest.fixture
def db(conn: Connection) -> Connection:
    """The rolled-back test connection with the six fixture accounts loaded."""
    for account_id, tz in ACCOUNTS.items():
        conn.execute(
            text("INSERT INTO accounts VALUES (:id, :name, 'Test', :tz, '2025-01-01 00:00:00')"),
            {"id": account_id, "name": f"A{account_id}", "tz": tz},
        )
    return conn


def add_event(
    conn: Connection,
    event_id: int,
    occurred_at: str,
    *,
    account: int = 1,
    location: str = "Site A",
    event_type: str = "call_received",
    duration: int | None = None,
    outcome: str | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO activity_events VALUES "
            "(:id, :account, :location, :type, :at, :duration, :outcome)"
        ),
        {
            "id": event_id,
            "account": account,
            "location": location,
            "type": event_type,
            "at": ts(occurred_at),
            "duration": duration,
            "outcome": outcome,
        },
    )


def clean_ids(conn: Connection) -> list[int]:
    return [r[0] for r in conn.execute(text("SELECT id FROM clean_events ORDER BY id"))]


# --- 6a. Dedupe -------------------------------------------------------------------------


def test_d1_exact_duplicate_keeps_lowest_id(db: Connection) -> None:
    add_event(db, 1, "2026-02-03 15:00:00", duration=600, outcome="connected")
    add_event(db, 2, "2026-02-03 15:00:00", duration=600, outcome="connected")
    assert clean_ids(db) == [1]


def test_d2_duplicate_with_null_columns_collapses(db: Connection) -> None:
    add_event(db, 3, "2026-02-03 16:00:00", event_type="lead_created")
    add_event(db, 4, "2026-02-03 16:00:00", event_type="lead_created")
    assert clean_ids(db) == [3]


def test_d3_null_vs_value_is_not_a_duplicate(db: Connection) -> None:
    add_event(db, 5, "2026-02-03 17:00:00", event_type="lead_created", outcome="open")
    add_event(db, 6, "2026-02-03 17:00:00", event_type="lead_created", duration=600, outcome="open")
    assert clean_ids(db) == [5, 6]


def test_d3b_null_outcome_vs_value_is_not_a_duplicate(db: Connection) -> None:
    add_event(db, 7, "2026-02-03 18:00:00", duration=600)
    add_event(db, 8, "2026-02-03 18:00:00", duration=600, outcome="missed")
    assert clean_ids(db) == [7, 8]


def test_d4_near_duplicates_are_kept(db: Connection) -> None:
    at = "2026-02-03 19:00:00"
    add_event(db, 9, at, duration=600, outcome="connected")  # base row
    add_event(db, 10, "2026-02-03 19:00:01", duration=600, outcome="connected")  # +1 second
    add_event(db, 11, at, duration=601, outcome="connected")  # different duration
    add_event(db, 12, at, event_type="lead_created", duration=600, outcome="connected")
    add_event(db, 13, at, location="Site B", duration=600, outcome="connected")
    add_event(db, 14, at, account=2, duration=600, outcome="connected")  # other account
    assert clean_ids(db) == [9, 10, 11, 12, 13, 14]


def test_d5_triple_insert_keeps_lowest_id_regardless_of_insert_order(db: Connection) -> None:
    for event_id in (30, 10, 20):
        add_event(db, event_id, "2026-02-04 09:00:00", duration=300, outcome="connected")
    assert clean_ids(db) == [10]


def test_d6_view_does_not_mutate_raw_table(db: Connection) -> None:
    add_event(db, 1, "2026-02-03 15:00:00", duration=600, outcome="connected")
    add_event(db, 2, "2026-02-03 15:00:00", duration=600, outcome="connected")
    assert clean_ids(db) == [1]
    assert db.execute(text("SELECT count(*) FROM activity_events")).scalar_one() == 2


# --- 6a. Normalization ------------------------------------------------------------------


def test_n1_event_type_is_trimmed_and_lowercased(db: Connection) -> None:
    add_event(db, 15, "2026-02-04 09:00:00", event_type=" Call_Received ")
    event_type = db.execute(text("SELECT event_type FROM clean_events WHERE id = 15")).scalar_one()
    assert event_type == "call_received"


def test_n2_location_is_trimmed_but_not_case_folded(db: Connection) -> None:
    add_event(db, 16, "2026-02-04 11:00:00", location=" Site A\t", duration=5, outcome="connected")
    add_event(db, 17, "2026-02-04 12:00:00", location="Site A", duration=5, outcome="connected")
    add_event(db, 18, "2026-02-04 13:00:00", location="site a", duration=5, outcome="connected")
    rows = db.execute(text("SELECT id, location FROM clean_events ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [(16, "Site A"), (17, "Site A"), (18, "site a")]
    assert db.execute(text("SELECT count(DISTINCT location) FROM clean_events")).scalar_one() == 2


def test_n3_dedupe_happens_after_normalization(db: Connection) -> None:
    add_event(db, 19, "2026-02-04 10:00:00", duration=5, outcome="connected")
    add_event(
        db, 20, "2026-02-04 10:00:00", event_type=" CALL_RECEIVED ", duration=5, outcome="connected"
    )
    assert clean_ids(db) == [19]


def test_n4_unknown_event_type_passes_through(db: Connection) -> None:
    add_event(db, 21, "2026-02-04 14:00:00", event_type="phone_call")
    event_type = db.execute(text("SELECT event_type FROM clean_events WHERE id = 21")).scalar_one()
    assert event_type == "phone_call"


def test_n5_view_columns(db: Connection) -> None:
    rows = db.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'clean_events' "
            "ORDER BY ordinal_position"
        )
    ).all()
    columns = [tuple(r) for r in rows]
    assert [name for name, _ in columns] == [
        "id",
        "account_id",
        "location",
        "event_type",
        "occurred_at",
        "duration_seconds",
        "outcome",
        "local_ts",
        "local_week",
    ]
    types = dict(columns)
    assert types["local_ts"] == "timestamp without time zone"
    assert types["local_week"] == "date"


# --- 6b. Timezone direction, week edges, DST --------------------------------------------

# (case, account, UTC occurred_at, expected local_ts, expected local_week, local week != UTC week)
TIME_CASES = [
    # Direction. Feb 1 2026 is a Sunday, so its week starts Mon Jan 26. CST: -6 h.
    ("T1", 1, "2026-02-01 16:39:22", "2026-02-01 10:39:22", "2026-01-26", False),
    # EDT -4 h: 03:30 UTC on Jul 1 is 23:30 on Jun 30 locally (wrong direction: Jul 1 07:30).
    ("T2", 6, "2026-07-01 03:30:00", "2026-06-30 23:30:00", "2026-06-29", False),
    # CDT -5 h in summer (a fixed -6 would give 10:39:22).
    ("T3", 1, "2026-07-01 16:39:22", "2026-07-01 11:39:22", "2026-06-29", False),
    # Chicago CST -6 h. 05:59:59 UTC Mon = 23:59:59 Sun; 06:00:00 UTC = 00:00:00 Mon.
    ("W1", 1, "2026-02-09 05:59:59", "2026-02-08 23:59:59", "2026-02-02", True),
    ("W2", 1, "2026-02-09 06:00:00", "2026-02-09 00:00:00", "2026-02-09", False),
    # UTC account: local == UTC.
    ("W3", 4, "2026-02-08 23:59:59", "2026-02-08 23:59:59", "2026-02-02", False),
    ("W4", 4, "2026-02-09 00:00:00", "2026-02-09 00:00:00", "2026-02-09", False),
    # Kolkata +5:30, ahead of UTC. 18:29:59 + 5:30 = 23:59:59; 18:30:00 + 5:30 = 00:00:00 next day.
    ("W5", 5, "2026-02-08 18:29:59", "2026-02-08 23:59:59", "2026-02-02", False),
    ("W6", 5, "2026-02-08 18:30:00", "2026-02-09 00:00:00", "2026-02-09", True),
    # DST. Chicago switches at 08:00 UTC on Mar 8: CST -6 before, CDT -5 from then on.
    ("S1", 1, "2026-03-08 07:59:59", "2026-03-08 01:59:59", "2026-03-02", False),
    ("S2", 1, "2026-03-08 08:00:00", "2026-03-08 03:00:00", "2026-03-02", False),  # no 02:xx
    # After DST (CDT -5): 04:59:59 UTC = 23:59:59 Sun; 05:00:00 UTC = 00:00:00 Mon.
    ("S3", 1, "2026-03-09 04:59:59", "2026-03-08 23:59:59", "2026-03-02", True),
    ("S4", 1, "2026-03-09 05:00:00", "2026-03-09 00:00:00", "2026-03-09", False),
    # Pre-DST control (CST -6): 05:59:59 UTC Mar 2 = 23:59:59 Sun Mar 1; 06:00:00 = 00:00:00 Mon.
    ("S5a", 1, "2026-03-02 05:59:59", "2026-03-01 23:59:59", "2026-02-23", True),
    ("S5b", 1, "2026-03-02 06:00:00", "2026-03-02 00:00:00", "2026-03-02", False),
    # Denver (MDT -6 since 09:00 UTC Mar 8) vs Phoenix (MST -7, never DST), same instant.
    ("P1-denver", 2, "2026-03-09 06:30:00", "2026-03-09 00:30:00", "2026-03-09", False),
    ("P1-phoenix", 3, "2026-03-09 06:30:00", "2026-03-08 23:30:00", "2026-03-02", True),
    # Control before DST: both -7 h, identical.
    ("P2-denver", 2, "2026-03-02 06:30:00", "2026-03-01 23:30:00", "2026-02-23", True),
    ("P2-phoenix", 3, "2026-03-02 06:30:00", "2026-03-01 23:30:00", "2026-02-23", True),
    # Summer repeat: Denver -6 h, Phoenix -7 h.
    ("P3-denver", 2, "2026-07-13 06:30:00", "2026-07-13 00:30:00", "2026-07-13", False),
    ("P3-phoenix", 3, "2026-07-13 06:30:00", "2026-07-12 23:30:00", "2026-07-06", True),
]


@pytest.mark.parametrize(
    ("account", "utc", "local_ts", "local_week", "differs_from_utc_week"),
    [pytest.param(*c[1:], id=c[0]) for c in TIME_CASES],
)
def test_local_time_and_week(
    db: Connection,
    account: int,
    utc: str,
    local_ts: str,
    local_week: str,
    differs_from_utc_week: bool,
) -> None:
    add_event(db, 1, utc, account=account)
    row = db.execute(
        text(
            "SELECT local_ts, local_week, "
            "       local_week <> date_trunc('week', occurred_at)::date AS differs "
            "FROM clean_events"
        )
    ).one()
    assert row.local_ts == ts(local_ts)
    assert row.local_week == date.fromisoformat(local_week)
    assert row.differs is differs_from_utc_week
