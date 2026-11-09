"""Domain value types. Frozen dataclasses; T3 maps them to API models."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Verdict(StrEnum):
    NORMAL = "normal"
    HIGHER = "higher"
    LOWER = "lower"
    NOT_ENOUGH_HISTORY = "not_enough_history"
    TOO_QUIET = "too_quiet"
    NO_ACTIVITY = "no_activity"


@dataclass(frozen=True)
class JudgeParams:
    baseline_weeks: int
    min_history_weeks: int
    z_min: float
    min_abs: float
    min_baseline_median: float


@dataclass(frozen=True)
class Baseline:
    median: float
    mad: float
    spread: float
    weeks_used: int
    band_low: float
    band_high: float


@dataclass(frozen=True)
class Judgement:
    verdict: Verdict
    x: int
    history_weeks: int
    baseline: Baseline | None
    z: float | None
    diff: float | None


@dataclass(frozen=True)
class WeekCounts:
    """One zero-filled local week. `unknown` counts event types outside the three known ones."""

    week: date
    call_received: int
    lead_created: int
    appointment_set: int
    unknown: int

    @property
    def total(self) -> int:
        """The metric (D-08): the three known types only. Unknown types never count."""
        return self.call_received + self.lead_created + self.appointment_set


@dataclass(frozen=True)
class Series:
    """Contiguous weekly counts, oldest first; the last element is the selected week.

    `key` is the location name, or None for the account rollup. `start_week` is when the
    series' subject first exists (it can be earlier than `weeks[0]` when the lookback clips it).
    """

    key: str | None
    start_week: date
    weeks: tuple[WeekCounts, ...]
