"""Seed anchors A1-A10 (plans/T2-backend-core.md §2g): the real data through series + judge.

A separate module on purpose: the module-scoped `seeded_conn` holds the seed's TRUNCATE locks
(ACCESS EXCLUSIVE) until it rolls back, so no test using the function-scoped `conn` may share
its module. Everything runs on `relay_test`; the dev database is never touched.

Expected values are the plan's hand-computed ones. Rounded values (z, spread) use a tight
relative tolerance because the plan shows them rounded.
"""

from collections.abc import Iterator
from datetime import date, datetime

import pytest
from sqlalchemy import Connection, Engine, text

from app.domain.models import Series, Verdict
from app.domain.verdict import judge
from app.domain.weeks import first_complete_week, last_complete_week
from app.seed import load_seed
from app.series import fetch_bounds, fetch_series, history_and_x
from app.settings import ReportSettings

FIRST = date(2026, 2, 2)
PARAMS = ReportSettings().judge_params()


@pytest.fixture(scope="module")
def seeded_conn(test_engine: Engine) -> Iterator[Connection]:
    with test_engine.connect() as connection:
        connection.begin()
        load_seed(connection)
        yield connection
        connection.rollback()


def location_series(conn: Connection, account: int, location: str, week: date) -> Series:
    result = fetch_series(conn, account, week, FIRST, PARAMS.baseline_weeks)
    return next(s for s in result.locations if s.key == location)


def test_a1_account_6_spike_week_is_higher(seeded_conn: Connection) -> None:
    result = fetch_series(seeded_conn, 6, date(2026, 6, 1), FIRST, PARAMS.baseline_weeks)
    assert result.account is not None
    history, x = history_and_x(result.account)
    # 12 prior weeks 03-09 .. 05-25 (view numbers; profile's 881 is the raw count)
    assert history == [84, 81, 71, 82, 76, 55, 64, 86, 68, 78, 62, 53]
    assert x == 880
    judgement = judge(history, x, PARAMS)
    assert judgement.verdict is Verdict.HIGHER
    assert judgement.baseline is not None
    assert judgement.baseline.weeks_used == 12
    assert judgement.baseline.median == 73.5
    assert judgement.baseline.mad == 9.0
    assert judgement.baseline.spread == pytest.approx(13.343, rel=1e-4)
    assert judgement.diff == 806.5
    assert judgement.z == pytest.approx(60.44, rel=1e-4)
    print(f"A1 median={judgement.baseline.median} MAD={judgement.baseline.mad} z={judgement.z!r}")


def test_a2_ordinary_location_is_normal(seeded_conn: Connection) -> None:
    site_a = location_series(seeded_conn, 1, "Site A", date(2026, 7, 20))
    history, x = history_and_x(site_a)
    assert history == [8, 7, 6, 6, 5, 7, 9, 11, 7, 10, 7, 9]
    assert x == 9
    judgement = judge(history, x, PARAMS)
    assert judgement.verdict is Verdict.NORMAL
    assert judgement.baseline is not None
    assert judgement.baseline.median == 7
    assert judgement.baseline.mad == 1
    assert judgement.baseline.spread == pytest.approx(2.646, rel=1e-3)
    assert judgement.diff == 2
    assert judgement.z == pytest.approx(0.756, rel=1e-3)
    print(f"A2 median={judgement.baseline.median} MAD={judgement.baseline.mad} z={judgement.z!r}")


def test_a3_account_20_has_no_activity(seeded_conn: Connection) -> None:
    result = fetch_series(seeded_conn, 20, date(2026, 7, 20), FIRST, PARAMS.baseline_weeks)
    assert result.has_events is False
    assert result.account is None
    judgement = judge([], 0, PARAMS, has_events=result.has_events)
    assert judgement.verdict is Verdict.NO_ACTIVITY


def test_a4_seven_prior_weeks_is_not_enough_history_eight_is_judged(
    seeded_conn: Connection,
) -> None:
    # complete weeks start 02-02: before 03-23 there are 02-02 .. 03-16 = 7; before 03-30 = 8
    early = history_and_x(location_series(seeded_conn, 1, "Site A", date(2026, 3, 23)))
    assert len(early[0]) == 7
    assert judge(early[0], early[1], PARAMS).verdict is Verdict.NOT_ENOUGH_HISTORY
    later = history_and_x(location_series(seeded_conn, 1, "Site A", date(2026, 3, 30)))
    assert len(later[0]) == 8
    judged = judge(later[0], later[1], PARAMS)
    assert judged.verdict is not Verdict.NOT_ENOUGH_HISTORY
    assert judged.baseline is not None
    assert judged.baseline.weeks_used == 8


def test_a5_last_and_first_complete_week_for_every_account(seeded_conn: Connection) -> None:
    data_start, as_of = fetch_bounds(seeded_conn)
    assert as_of == datetime(2026, 7, 27, 22, 20, 34)
    assert data_start == datetime(2026, 2, 1, 10, 57, 44)
    zones = seeded_conn.execute(text("SELECT id, timezone FROM accounts ORDER BY id")).all()
    assert len(zones) == 20
    for account_id, tz in zones:
        assert last_complete_week(as_of, tz) == date(2026, 7, 20), (account_id, tz)
        assert first_complete_week(data_start, tz) == FIRST, (account_id, tz)


def test_a6_real_series_has_an_explicit_zero_week(seeded_conn: Connection) -> None:
    site_g = location_series(seeded_conn, 6, "Site G", date(2026, 7, 13))
    by_week = {w.week: w.total for w in site_g.weeks}
    assert len(site_g.weeks) == 13  # 12 prior weeks 04-20 .. 07-06 plus W
    assert by_week[date(2026, 6, 29)] == 0
    assert by_week[date(2026, 6, 1)] == 57


def test_a7_all_69_locations_are_present_with_full_windows(seeded_conn: Connection) -> None:
    per_account = {
        account_id: fetch_series(
            seeded_conn, account_id, date(2026, 7, 20), FIRST, PARAMS.baseline_weeks
        )
        for account_id in range(1, 21)
    }
    assert sum(len(r.locations) for r in per_account.values()) == 69
    assert len(per_account[6].locations) == 15
    for result in per_account.values():
        for series in result.locations:
            assert len(series.weeks) == 13


def test_a8_seed_has_no_unknown_event_types(seeded_conn: Connection) -> None:
    for account_id in range(1, 21):
        result = fetch_series(seeded_conn, account_id, date(2026, 7, 20), FIRST, 12)
        for series in result.locations:
            assert sum(w.unknown for w in series.weeks) == 0, (account_id, series.key)


def test_a9_zero_week_in_location_baseline_is_normal(seeded_conn: Connection) -> None:
    site_g = location_series(seeded_conn, 6, "Site G", date(2026, 7, 20))
    history, x = history_and_x(site_g)
    assert history == [6, 4, 3, 7, 5, 57, 4, 5, 3, 0, 4, 6]
    assert x == 6
    judgement = judge(history, x, PARAMS)
    assert judgement.verdict is Verdict.NORMAL
    assert judgement.baseline is not None
    assert judgement.baseline.weeks_used == 12
    assert judgement.baseline.median == 4.5
    assert judgement.baseline.mad == 1.5
    assert judgement.baseline.spread == pytest.approx(2.2239, rel=1e-4)
    assert judgement.diff == 1.5
    assert judgement.z == pytest.approx(0.674, rel=1e-3)


def test_a10_real_data_boundary_z_exactly_minus_two_is_lower(seeded_conn: Connection) -> None:
    site_b = location_series(seeded_conn, 9, "Site B", date(2026, 5, 4))
    history, x = history_and_x(site_b)
    assert history == [11, 10, 8, 4, 8, 7, 9, 9, 9, 8, 14, 10]
    assert x == 3
    judgement = judge(history, x, PARAMS)
    assert judgement.verdict is Verdict.LOWER
    assert judgement.baseline is not None
    assert judgement.baseline.weeks_used == 12
    assert judgement.baseline.median == 9
    assert judgement.baseline.mad == 1
    assert judgement.baseline.spread == 3.0
    assert judgement.diff == -6
    assert judgement.z == -2.0
