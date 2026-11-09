"""Fact lines: the only place summary text is made (plans/T5-ai-summary.md §1c).

Names and numbers come from the facts, never from the model. Formats follow the frontend.
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models import Verdict
from app.summary.claims import Claim
from app.summary.facts import FLAGGED, Band, LocationFacts, SummaryFacts


def fmt_num(value: float) -> str:
    """At most one decimal, trailing `.0` dropped, half rounded up like the frontend."""
    text = str(Decimal(repr(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    text = text.removesuffix(".0")
    return "0" if text in ("-0", "-0.0") else text


def fmt_diff(value: float) -> str:
    magnitude = fmt_num(abs(value))
    if magnitude == "0":
        return "0"
    return ("+" if value > 0 else "−") + magnitude


def fmt_band(band: Band) -> str:
    return f"{fmt_num(band[0])} to {fmt_num(band[1])}"


def _direction(verdict: Verdict) -> str:
    return "higher" if verdict == Verdict.HIGHER else "lower"


def _account_line(facts: SummaryFacts) -> str:
    account = facts.account
    verdict = account.verdict
    if verdict == Verdict.NO_ACTIVITY:
        return "No activity has been recorded for this account."
    if facts.week is None:
        return "No week can be judged yet for this account: not enough history."
    week = f"Week of {facts.week.isoformat()}"
    if verdict == Verdict.NOT_ENOUGH_HISTORY:
        return f"{week}: not enough history to judge this account."
    if account.median is None or account.band is None or account.total is None:
        raise ValueError(f"account verdict {verdict} without a baseline")
    if verdict == Verdict.TOO_QUIET:
        return (
            f"{week}: this account is too quiet to judge "
            f"(usual weekly total {fmt_num(account.median)}, "
            f"below {fmt_num(facts.min_baseline_median)})."
        )
    if verdict == Verdict.NORMAL:
        return (
            f"{week}: {account.total} events, within the usual range "
            f"({fmt_band(account.band)}) for this account."
        )
    return (
        f"{week}: {account.total} events, {_direction(verdict)} than usual "
        f"({fmt_band(account.band)}) for this account."
    )


def _location_line(name: str, location: LocationFacts) -> str:
    assert location.verdict in FLAGGED
    return (
        f"{name}: {location.total} events, {_direction(location.verdict)} than usual "
        f"({fmt_band(location.band)}); {fmt_diff(location.diff)} against the usual "
        f"{fmt_num(location.median)}."
    )


def fact_lines(facts: SummaryFacts, claims: Sequence[Claim]) -> list[str]:
    """The account line, one line per location claim in claim order, then the counts."""
    lines = [_account_line(facts)]
    if facts.week is None:
        return lines
    for claim in claims:
        if claim.scope == "location" and claim.location is not None:
            lines.append(
                _location_line(facts.names[claim.location], facts.location(claim.location))
            )
    if facts.flagged_total == 0:
        lines.append("No locations were flagged this week.")
    elif facts.flagged_total > len(facts.locations):
        lines.append(
            f"More flagged locations not listed: {facts.flagged_total - len(facts.locations)}."
        )
    if facts.not_judged_total > 0:
        lines.append(f"Locations that could not be judged: {facts.not_judged_total}.")
    return lines


def claims_from_facts(facts: SummaryFacts) -> list[Claim]:
    """The template's claims: the account, then every listed location in report order."""
    claims = [Claim(scope="account", location=None, metric="total", verdict=facts.account.verdict)]
    claims += [
        Claim(scope="location", location=loc.id, metric="total", verdict=loc.verdict)
        for loc in facts.locations
    ]
    return claims


def template_lines(facts: SummaryFacts) -> list[str]:
    return fact_lines(facts, claims_from_facts(facts))
