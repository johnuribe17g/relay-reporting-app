"""Lightweight backtest (PLAN §9, plans/T3-backend-api.md §2d). Assertions fixed before any run.

Calls `build_report`, the service the endpoints call, with the real params for every account that
has events and every selectable week of that account. It is a sanity check, not a tuning exercise:
if B3 fails we stop and discuss; no parameter and no ceiling is changed to make it pass.
Run `pytest -s tests/api/test_backtest.py` to see the recorded numbers.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from sqlalchemy import Connection

from app.deps import Account, Bounds
from app.report import build_report, build_weeks
from app.schemas import Report
from app.series import fetch_accounts, fetch_bounds
from app.settings import ReportSettings

PARAMS = ReportSettings().judge_params()
SPIKE_ACCOUNT = 6
SPIKE_WEEK = "2026-06-01"
CEILING = 0.08  # B3: 8.0 %, fixed before the first run (plan §2d, Q8)
FLAGGED = {"higher", "lower"}


@dataclass
class Backtest:
    reports: dict[tuple[int, str], Report] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def spike(self) -> Report:
        return self.reports[(SPIKE_ACCOUNT, SPIKE_WEEK)]

    def location_weeks(self) -> Iterator[tuple[int, str, str, float | None]]:
        """(account, week, verdict, z) of every location-week outside account 6's spike week."""
        for (account, week), report in self.reports.items():
            if (account, week) == (SPIKE_ACCOUNT, SPIKE_WEEK):
                continue
            for row in report.locations:
                yield account, week, row.verdict.value, row.z


@pytest.fixture(scope="module")
def backtest(seeded_conn: Connection) -> Backtest:
    result = Backtest()
    data_start, as_of = fetch_bounds(seeded_conn)
    bounds = Bounds(data_start=data_start, as_of=as_of)
    for row in fetch_accounts(seeded_conn):
        account = Account(id=row.id, name=row.name, timezone=row.timezone)
        for week in build_weeks(seeded_conn, account, PARAMS, bounds).weeks:
            try:
                result.reports[(account.id, week.isoformat())] = build_report(
                    seeded_conn, account, week.isoformat(), PARAMS, bounds
                )
            except Exception as exc:  # noqa: BLE001 - B5 reports it
                result.errors.append(f"account {account.id} week {week}: {exc!r}")
    return result


def test_b1_account_6_spike_week_is_higher_at_account_level(backtest: Backtest) -> None:
    summary = backtest.spike().account_summary
    assert summary.verdict.value == "higher"
    assert summary.total == 880
    assert summary.z == pytest.approx(60.44, abs=0.01)


def test_b2_every_judged_location_flags_at_the_spike_week(backtest: Backtest) -> None:
    rows = backtest.spike().locations
    judged = [r for r in rows if r.z is not None]
    flagged = [r for r in judged if r.verdict.value == "higher"]
    unjudged = [r for r in rows if r.z is None]
    print(
        f"\nB2 account 6 at {SPIKE_WEEK}: {len(rows)} locations, {len(judged)} judged, "
        f"{len(flagged)} flagged higher, {len(unjudged)} unjudged "
        f"({sorted((r.location, r.verdict.value) for r in unjudged)})"
    )
    assert len(rows) == 15
    assert len(judged) >= 1
    assert all(r.verdict.value == "higher" for r in judged)


def test_b3_flag_rate_outside_the_spike_week_is_under_the_ceiling(backtest: Backtest) -> None:
    cells = list(backtest.location_weeks())
    judged = [c for c in cells if c[3] is not None]
    flagged = [c for c in judged if c[2] in FLAGGED]
    higher = [c for c in flagged if c[2] == "higher"]
    unjudged = [c for c in cells if c[3] is None]
    by_verdict = {
        v: sum(1 for c in unjudged if c[2] == v) for v in sorted({c[2] for c in unjudged})
    }
    rate = len(flagged) / len(judged)

    account_cells = [
        r.account_summary
        for (account, week), r in backtest.reports.items()
        if (account, week) != (SPIKE_ACCOUNT, SPIKE_WEEK)
    ]
    account_judged = [s for s in account_cells if s.z is not None]
    account_flagged = [s for s in account_judged if s.verdict.value in FLAGGED]

    print(
        f"\nB3 parameters used: {PARAMS}"
        f"\nB3 reports: {len(backtest.reports)}; "
        f"location-weeks outside the spike week: {len(cells)}"
        f"\n   judged: {len(judged)}, flagged: {len(flagged)}, "
        f"rate: {rate:.2%} (ceiling {CEILING:.1%})"
        f"\n   higher: {len(higher)}, lower: {len(flagged) - len(higher)}"
        f"\n   unjudged: {len(unjudged)} {by_verdict}"
        f"\n   account level: judged {len(account_judged)}, flagged {len(account_flagged)}, "
        f"rate {len(account_flagged) / len(account_judged):.2%}"
    )
    assert judged
    assert rate <= CEILING


def test_b4_no_account_level_not_enough_history_in_the_selectable_range(
    backtest: Backtest,
) -> None:
    bad = [
        key
        for key, report in backtest.reports.items()
        if report.account_summary.verdict.value == "not_enough_history"
    ]
    assert backtest.reports
    assert bad == []


def test_b5_no_exception_and_no_history_longer_than_the_baseline(backtest: Backtest) -> None:
    assert backtest.errors == []
    for report in backtest.reports.values():
        rows = [report.account_summary, *report.locations]
        assert all(r.history_weeks <= PARAMS.baseline_weeks for r in rows)
