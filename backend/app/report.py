"""Report service: selectable weeks, week validation, and the report builders (plans/T3 §1c)."""

from datetime import date, timedelta

from app.errors import ApiError


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


def resolve_week(week: str | None, weeks: list[date]) -> date | None:
    """The default (last selectable) week when omitted, else the given week if it is listed."""
    if week is None:
        return weeks[-1] if weeks else None
    if not weeks:
        raise ApiError(422, "invalid_week", "no selectable weeks for this account")
    try:
        parsed = date.fromisoformat(week)
    except ValueError:
        raise ApiError(422, "invalid_week", "week must be a date, YYYY-MM-DD") from None
    if parsed not in weeks:
        raise ApiError(
            422,
            "invalid_week",
            f"week must be a Monday in the selectable range {weeks[0].isoformat()} .. "
            f"{weeks[-1].isoformat()}",
        )
    return parsed
