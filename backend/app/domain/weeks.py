"""Week arithmetic in account-local time. The only timezone code in T2 (plan §1c).

Inputs are naive UTC datetimes, like `occurred_at` in the database. Weeks are ISO Mondays.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


def _local(utc_naive: datetime, tz: str) -> datetime:
    if utc_naive.tzinfo is not None:
        raise ValueError("expected a naive datetime holding UTC")
    return utc_naive.replace(tzinfo=UTC).astimezone(ZoneInfo(tz))


def _monday(local: datetime) -> date:
    return local.date() - timedelta(days=local.weekday())


def last_complete_week(as_of_utc: datetime, tz: str) -> date:
    """Monday of the last week that ended on or before `as_of` (its local Sunday is over)."""
    return _monday(_local(as_of_utc, tz)) - timedelta(days=7)


def first_complete_week(data_start_utc: datetime, tz: str) -> date:
    """Monday of the first week fully covered by data starting at `data_start`.

    The week containing the start is partial unless the start is exactly Monday 00:00:00 local.
    """
    local = _local(data_start_utc, tz)
    monday = _monday(local)
    if local.replace(tzinfo=None) == datetime.combine(monday, datetime.min.time()):
        return monday
    return monday + timedelta(days=7)
