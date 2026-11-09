"""Zero-filled weekly series over `clean_events` (plans/T2-backend-core.md §1d).

SQL only builds the counts; every statistic lives in `app.domain`. Weeks come from the view's
`local_week`, so there is no time-zone logic here.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Connection, text

from app.domain.models import Series, WeekCounts

_SERIES_SQL = text(
    """
WITH ev AS (   -- the account's events, bucketed by the view's local_week
    SELECT location, local_week, event_type
    FROM clean_events WHERE account_id = :account_id
),
loc AS (       -- a location exists only through events (no locations table)
    SELECT location, GREATEST(min(local_week), CAST(:first_week AS date)) AS start_week
    FROM ev GROUP BY location
    -- An empty generate_series range would also exclude locations starting after W; this states it.
    HAVING GREATEST(min(local_week), CAST(:first_week AS date)) <= CAST(:week AS date)
),
grid AS (      -- zero-filled grid: the last `lookback_weeks` prior weeks plus the selected week
    SELECT l.location, l.start_week, CAST(w AS date) AS week
    FROM loc l
    CROSS JOIN LATERAL generate_series(
        CAST(GREATEST(l.start_week,
                      CAST(:week AS date) - CAST(:lookback_weeks AS integer) * 7) AS timestamp),
        CAST(CAST(:week AS date) AS timestamp),
        interval '7 days'
    ) AS w
)
SELECT g.location, g.start_week, g.week,
       count(*) FILTER (WHERE e.event_type = 'call_received')   AS call_received,
       count(*) FILTER (WHERE e.event_type = 'lead_created')    AS lead_created,
       count(*) FILTER (WHERE e.event_type = 'appointment_set') AS appointment_set,
       count(*) FILTER (
           WHERE e.event_type NOT IN ('call_received', 'lead_created', 'appointment_set')
       ) AS unknown
FROM grid g
LEFT JOIN ev e ON e.location = g.location AND e.local_week = g.week
GROUP BY g.location, g.start_week, g.week
ORDER BY g.location, g.week
"""
)

_HAS_EVENTS_SQL = text("SELECT EXISTS (SELECT 1 FROM clean_events WHERE account_id = :account_id)")
_BOUNDS_SQL = text("SELECT min(occurred_at), max(occurred_at) FROM clean_events")


@dataclass(frozen=True)
class AccountSeries:
    """An account's rollup series and its locations' series up to the selected week.

    `account` is None when no location exists at the selected week: either the account has no
    events at all (`has_events` False) or all its locations start after that week.
    """

    account_id: int
    has_events: bool
    account: Series | None
    locations: tuple[Series, ...]


def fetch_bounds(conn: Connection) -> tuple[datetime | None, datetime | None]:
    """Global (min, max) `occurred_at` of the view: the default data start and as-of."""
    row = conn.execute(_BOUNDS_SQL).one()
    return row[0], row[1]


def _require_monday(name: str, value: date) -> None:
    if value.weekday() != 0:
        raise ValueError(f"{name} must be a Monday, got {value.isoformat()}")


def fetch_series(
    conn: Connection,
    account_id: int,
    week: date,
    first_complete_week: date,
    lookback_weeks: int,
) -> AccountSeries:
    """Zero-filled weekly counts per location and for the account, ending at `week`.

    A location takes part only if it starts on or before `week` (no future data); it starts at
    its first event week, never before `first_complete_week`. A silent week stays as a row of zeros.
    """
    _require_monday("week", week)
    _require_monday("first_complete_week", first_complete_week)

    rows = conn.execute(
        _SERIES_SQL,
        {
            "account_id": account_id,
            "week": week,
            "first_week": first_complete_week,
            "lookback_weeks": lookback_weeks,
        },
    ).all()
    has_events = bool(conn.execute(_HAS_EVENTS_SQL, {"account_id": account_id}).scalar_one())

    by_location: dict[str, list[WeekCounts]] = defaultdict(list)
    starts: dict[str, date] = {}
    for location, start_week, row_week, calls, leads, appointments, unknown in rows:
        starts[location] = start_week
        by_location[location].append(WeekCounts(row_week, calls, leads, appointments, unknown))

    locations = tuple(
        Series(key=name, start_week=starts[name], weeks=tuple(by_location[name]))
        for name in sorted(by_location)
    )
    return AccountSeries(
        account_id=account_id,
        has_events=has_events,
        account=_rollup(locations),
        locations=locations,
    )


def _rollup(locations: tuple[Series, ...]) -> Series | None:
    """Per-week sum of the location series, from the earliest location start."""
    if not locations:
        return None
    sums: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for series in locations:
        for w in series.weeks:
            acc = sums[w.week]
            acc[0] += w.call_received
            acc[1] += w.lead_created
            acc[2] += w.appointment_set
            acc[3] += w.unknown
    weeks = tuple(WeekCounts(week, *sums[week]) for week in sorted(sums))
    return Series(key=None, start_week=min(s.start_week for s in locations), weeks=weeks)


def history_and_x(series: Series) -> tuple[list[int], int]:
    """Split a series into the prior weekly totals (oldest first) and the selected week's total."""
    totals = [w.total for w in series.weeks]
    return totals[:-1], totals[-1]
