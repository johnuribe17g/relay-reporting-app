"""Hand-built `Report` fixtures F1 to F5 (plans/T5-ai-summary.md §2). No database."""

from datetime import date, datetime

from app.domain.models import Verdict
from app.schemas import (
    AccountOut,
    BaselineOut,
    ByType,
    DataQuality,
    LocationRow,
    Parameters,
    Report,
    Summary,
)

WEEK = date(2026, 7, 20)
ACCOUNT_NAME = "Acme Dental Group"


def summary(
    verdict: Verdict,
    total: int | None = None,
    median: float | None = None,
    band: tuple[float, float] | None = None,
    diff: float | None = None,
    history_weeks: int = 12,
) -> Summary:
    baseline = (
        None
        if median is None or band is None
        else BaselineOut(
            median=median,
            mad=0.0,
            spread=1.0,
            weeks_used=12,
            band_low=band[0],
            band_high=band[1],
        )
    )
    return Summary(
        total=total,
        verdict=verdict,
        z=None,
        diff=diff,
        history_weeks=history_weeks,
        baseline=baseline,
        by_type=None
        if total is None
        else ByType(call_received=total, lead_created=0, appointment_set=0),
        data_quality=DataQuality(unknown_events_in_window=0),
    )


def location(
    name: str,
    verdict: Verdict,
    total: int | None = None,
    median: float | None = None,
    band: tuple[float, float] | None = None,
    diff: float | None = None,
    history_weeks: int = 12,
) -> LocationRow:
    return LocationRow(
        location=name, **summary(verdict, total, median, band, diff, history_weeks).model_dump()
    )


def report(
    account: Summary,
    locations: list[LocationRow],
    week: date | None = WEEK,
    min_baseline_median: float = 4.0,
) -> Report:
    return Report(
        account=AccountOut(id=15, name=ACCOUNT_NAME, timezone="America/Chicago"),
        week=week,
        as_of=datetime(2026, 7, 27, 22, 20),
        parameters=Parameters(
            baseline_weeks=12,
            min_history_weeks=8,
            z_min=2.0,
            min_abs=3.0,
            min_baseline_median=min_baseline_median,
        ),
        account_summary=account,
        locations=locations,
    )


ACCOUNT_NORMAL = summary(Verdict.NORMAL, 20, 19.0, (7.1392, 30.8608))
SITE_C = location("Site C", Verdict.HIGHER, 12, 5.5, (0.8096, 10.1904), 6.5)
SITE_B = location("Site B", Verdict.NORMAL, 2, 6.5, (3.0, 10.0), -4.5)
SITE_A = location("Site A", Verdict.NORMAL, 6, 7.0, (1.7085, 12.2915), -1.0)
SITE_D = location("Site D", Verdict.LOWER, 2, 7.0, (3.5, 10.5), -5.0)


def f1() -> Report:
    """Account 15 at 2026-07-20 (T3 S5/S6): one flagged location, Site C higher."""
    return report(ACCOUNT_NORMAL, [SITE_C, SITE_B, SITE_A])


def f2() -> Report:
    """F1 with Site C normal: nothing flagged."""
    normal_c = location("Site C", Verdict.NORMAL, 12, 5.5, (0.8096, 10.1904), 6.5)
    return report(ACCOUNT_NORMAL, [normal_c, SITE_B, SITE_A])


def f3() -> Report:
    """Account normal, three locations that could not be judged."""
    return report(
        ACCOUNT_NORMAL,
        [
            location("Young 1", Verdict.NOT_ENOUGH_HISTORY, history_weeks=5),
            location("Young 2", Verdict.NOT_ENOUGH_HISTORY, history_weeks=5),
            location("Quiet", Verdict.TOO_QUIET, 3, 3.5, (0.0, 7.0)),
        ],
    )


def f4() -> Report:
    """Seven flagged locations (the cap is five)."""
    rows = [
        location(f"Loc{i}", Verdict.HIGHER, 9 + i, 5.0, (-0.5, 8.0), float(4 + i))
        for i in range(1, 8)
    ]
    return report(ACCOUNT_NORMAL, rows)


def f5() -> Report:
    """F1 plus Site D, lower: ids L1 = Site C (higher), L2 = Site D (lower)."""
    return report(ACCOUNT_NORMAL, [SITE_C, SITE_D, SITE_B, SITE_A])


def with_account_verdict(base: Report, verdict: Verdict) -> Report:
    account = summary(verdict, 20, 19.0, (7.1392, 30.8608))
    return base.model_copy(update={"account_summary": account})


def empty_report(verdict: Verdict) -> Report:
    return report(summary(verdict, history_weeks=0), [], week=None)
