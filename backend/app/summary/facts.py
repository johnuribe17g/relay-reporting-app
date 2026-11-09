"""The summary facts: the only data a provider ever sees (plans/T5-ai-summary.md §1b).

Built from the already-computed `Report`. Locations get ids `L1`..`L5`; their names stay in
`names` on the server and are never part of `prompt_payload`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.models import Verdict
from app.schemas import Report

MAX_LOCATIONS = 5
FLAGGED = (Verdict.HIGHER, Verdict.LOWER)
NOT_JUDGED = (Verdict.NOT_ENOUGH_HISTORY, Verdict.TOO_QUIET)

Band = tuple[float, float]


@dataclass(frozen=True)
class AccountFacts:
    verdict: Verdict
    total: int | None
    median: float | None
    band: Band | None


@dataclass(frozen=True)
class LocationFacts:
    id: str
    verdict: Verdict
    total: int
    median: float
    band: Band
    diff: float


@dataclass(frozen=True)
class SummaryFacts:
    week: date | None
    min_baseline_median: float
    account: AccountFacts
    locations: tuple[LocationFacts, ...]
    names: Mapping[str, str]
    flagged_total: int
    not_judged_total: int

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(location.id for location in self.locations)

    def location(self, location_id: str) -> LocationFacts:
        return next(loc for loc in self.locations if loc.id == location_id)


def _band(low: float, high: float) -> Band:
    # The display rule of D-17: the lower edge is never shown below 0.
    return (max(low, 0.0), high)


def build_facts(report: Report) -> SummaryFacts:
    summary = report.account_summary
    baseline = summary.baseline
    account = AccountFacts(
        verdict=summary.verdict,
        total=summary.total,
        median=None if baseline is None else baseline.median,
        band=None if baseline is None else _band(baseline.band_low, baseline.band_high),
    )
    flagged = [row for row in report.locations if row.verdict in FLAGGED]
    listed: list[LocationFacts] = []
    names: dict[str, str] = {}
    for index, row in enumerate(flagged[:MAX_LOCATIONS], start=1):
        if row.baseline is None or row.total is None or row.diff is None:
            raise ValueError(f"flagged location {row.location!r} has no baseline")
        location_id = f"L{index}"
        names[location_id] = row.location
        listed.append(
            LocationFacts(
                id=location_id,
                verdict=row.verdict,
                total=row.total,
                median=row.baseline.median,
                band=_band(row.baseline.band_low, row.baseline.band_high),
                diff=row.diff,
            )
        )
    return SummaryFacts(
        week=report.week,
        min_baseline_median=report.parameters.min_baseline_median,
        account=account,
        locations=tuple(listed),
        names=names,
        flagged_total=len(flagged),
        not_judged_total=sum(1 for row in report.locations if row.verdict in NOT_JUDGED),
    )


def prompt_payload(facts: SummaryFacts) -> dict[str, Any]:
    """What a provider sees: ids and numbers, never a location or account name."""
    account = facts.account
    return {
        "week": None if facts.week is None else facts.week.isoformat(),
        "account": {
            "verdict": account.verdict.value,
            "total": account.total,
            "median": account.median,
            "band": None if account.band is None else list(account.band),
        },
        "locations": [
            {
                "id": loc.id,
                "verdict": loc.verdict.value,
                "total": loc.total,
                "median": loc.median,
                "band": list(loc.band),
                "diff": loc.diff,
            }
            for loc in facts.locations
        ],
        "flagged_total": facts.flagged_total,
        "not_judged_total": facts.not_judged_total,
    }
