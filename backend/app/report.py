"""Report service: selectable weeks, week validation, and the report builders (plans/T3 §1c)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Connection

from app.deps import Account, Bounds
from app.domain.models import Baseline, Judgement, JudgeParams, Series, Verdict, WeekCounts
from app.domain.ranking import rank
from app.domain.verdict import judge
from app.domain.weeks import first_complete_week, last_complete_week
from app.errors import ApiError
from app.schemas import (
    AccountOut,
    BaselineOut,
    ByType,
    DataQuality,
    History,
    LocationRow,
    Parameters,
    Report,
    Summary,
    WeekPoint,
    WeeksOut,
)
from app.series import fetch_account_start, fetch_series, history_and_x


def weeks_range(start: date | None, last: date | None, min_history_weeks: int) -> list[date]:
    """Selectable Mondays: from `start + min_history_weeks` weeks through `last`, inclusive.

    `start` is the account's first week (None: no events); `last` its last complete week
    (None: no data bounds). The first week is the first where the account series has
    `min_history_weeks` prior weeks, so an account verdict is never `not_enough_history` inside it.
    """
    if start is None or last is None:
        return []
    first = start + timedelta(weeks=min_history_weeks)
    count = (last - first).days // 7 + 1
    return [first + timedelta(weeks=i) for i in range(max(count, 0))]


def _parse_date(value: str) -> date:
    """Strictly YYYY-MM-DD: `fromisoformat` also takes `20260216` and `2026-W08-1`."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        parsed = None
    # strptime accepts unpadded fields such as 2026-2-16; the round trip rejects them.
    if parsed is None or parsed.isoformat() != value:
        raise ApiError(422, "invalid_week", "week must be a date, YYYY-MM-DD")
    return parsed


def resolve_week(week: str | None, weeks: list[date]) -> date | None:
    """The default (last selectable) week when omitted, else the given week if it is listed."""
    if week is None:
        return weeks[-1] if weeks else None
    if not weeks:
        raise ApiError(422, "invalid_week", "no selectable weeks for this account")
    parsed = _parse_date(week)
    if parsed not in weeks:
        raise ApiError(
            422,
            "invalid_week",
            f"week must be a Monday in the selectable range {weeks[0].isoformat()} .. "
            f"{weeks[-1].isoformat()}",
        )
    return parsed


@dataclass(frozen=True)
class Selectable:
    """What an account may select: its weeks, plus what `fetch_series` needs."""

    weeks: list[date]
    first_complete: date | None
    has_events: bool


def selectable(
    conn: Connection, account: Account, params: JudgeParams, bounds: Bounds
) -> Selectable:
    """The account's selectable weeks in its own time zone (plans/T3 §1c)."""
    if bounds.data_start is None or bounds.as_of is None:
        return Selectable([], None, False)
    first = first_complete_week(bounds.data_start, account.timezone)
    last = last_complete_week(bounds.as_of, account.timezone)
    start = fetch_account_start(conn, account.id, first)
    weeks = weeks_range(start, last, params.min_history_weeks)
    return Selectable(weeks, first, start is not None)


def _account_out(account: Account) -> AccountOut:
    return AccountOut(id=account.id, name=account.name, timezone=account.timezone)


def _parameters(params: JudgeParams) -> Parameters:
    return Parameters(
        baseline_weeks=params.baseline_weeks,
        min_history_weeks=params.min_history_weeks,
        z_min=params.z_min,
        min_abs=params.min_abs,
        min_baseline_median=params.min_baseline_median,
    )


def _as_of(bounds: Bounds) -> datetime | None:
    return None if bounds.as_of is None else bounds.as_of.replace(tzinfo=UTC)


def _baseline(baseline: Baseline | None) -> BaselineOut | None:
    if baseline is None:
        return None
    return BaselineOut(
        median=baseline.median,
        mad=baseline.mad,
        spread=baseline.spread,
        weeks_used=baseline.weeks_used,
        band_low=baseline.band_low,
        band_high=baseline.band_high,
    )


def _by_type(week: WeekCounts) -> ByType:
    return ByType(
        call_received=week.call_received,
        lead_created=week.lead_created,
        appointment_set=week.appointment_set,
    )


def _data_quality(series: Series) -> DataQuality:
    return DataQuality(unknown_events_in_window=sum(w.unknown for w in series.weeks))


def _summary(series: Series, judgement: Judgement) -> Summary:
    selected = series.weeks[-1]
    return Summary(
        total=selected.total,
        verdict=judgement.verdict,
        z=judgement.z,
        diff=judgement.diff,
        history_weeks=judgement.history_weeks,
        baseline=_baseline(judgement.baseline),
        by_type=_by_type(selected),
        data_quality=_data_quality(series),
    )


def _empty_summary(verdict: Verdict) -> Summary:
    return Summary(
        total=None,
        verdict=verdict,
        z=None,
        diff=None,
        history_weeks=0,
        baseline=None,
        by_type=None,
        data_quality=DataQuality(unknown_events_in_window=0),
    )


def build_weeks(
    conn: Connection, account: Account, params: JudgeParams, bounds: Bounds
) -> WeeksOut:
    sel = selectable(conn, account, params, bounds)
    return WeeksOut(
        account=_account_out(account),
        weeks=sel.weeks,
        default_week=sel.weeks[-1] if sel.weeks else None,
        as_of=_as_of(bounds),
    )


def build_report(
    conn: Connection,
    account: Account,
    week: str | None,
    params: JudgeParams,
    bounds: Bounds,
) -> Report:
    """The report for the account at `week` (default: last selectable). Used by API and backtest."""
    sel = selectable(conn, account, params, bounds)
    selected = resolve_week(week, sel.weeks)
    if selected is None or sel.first_complete is None:
        # No selectable week: no events at all (T2's no_activity) or none judgeable yet.
        verdict = Verdict.NOT_ENOUGH_HISTORY if sel.has_events else Verdict.NO_ACTIVITY
        return Report(
            account=_account_out(account),
            week=None,
            as_of=_as_of(bounds),
            parameters=_parameters(params),
            account_summary=_empty_summary(verdict),
            locations=[],
        )

    fetched = fetch_series(conn, account.id, selected, sel.first_complete, params.baseline_weeks)
    if fetched.account is None:
        account_summary = _empty_summary(
            Verdict.NOT_ENOUGH_HISTORY if fetched.has_events else Verdict.NO_ACTIVITY
        )
    else:
        history, x = history_and_x(fetched.account)
        account_summary = _summary(
            fetched.account, judge(history, x, params, has_events=fetched.has_events)
        )

    by_location: dict[str, Series] = {s.key: s for s in fetched.locations if s.key is not None}
    judged = [(name, judge(*history_and_x(series), params)) for name, series in by_location.items()]
    locations = [
        LocationRow(location=name, **_summary(by_location[name], judgement).model_dump())
        for name, judgement in rank(judged)
    ]
    return Report(
        account=_account_out(account),
        week=selected,
        as_of=_as_of(bounds),
        parameters=_parameters(params),
        account_summary=account_summary,
        locations=locations,
    )


def build_history(
    conn: Connection,
    account: Account,
    location: str,
    week: str | None,
    params: JudgeParams,
    bounds: Bounds,
) -> History:
    """A location's weekly totals around `week` with the one band of the selected week."""
    sel = selectable(conn, account, params, bounds)
    selected = resolve_week(week, sel.weeks)
    if selected is None or sel.first_complete is None:
        raise ApiError(
            404,
            "location_not_found",
            f"account has no selectable week, so no location {location!r}",
        )
    fetched = fetch_series(conn, account.id, selected, sel.first_complete, params.baseline_weeks)
    series = next((s for s in fetched.locations if s.key == location), None)
    if series is None:
        raise ApiError(
            404,
            "location_not_found",
            f"location {location!r} does not exist at week {selected.isoformat()}",
        )
    judgement = judge(*history_and_x(series), params)
    last = len(series.weeks) - 1
    return History(
        account=_account_out(account),
        location=location,
        week=selected,
        as_of=_as_of(bounds),
        parameters=_parameters(params),
        verdict=judgement.verdict,
        z=judgement.z,
        diff=judgement.diff,
        baseline=_baseline(judgement.baseline),
        weeks=[
            WeekPoint(
                week=w.week,
                total=w.total,
                by_type=_by_type(w),
                role="selected" if i == last else "baseline",
            )
            for i, w in enumerate(series.weeks)
        ],
        data_quality=_data_quality(series),
    )
