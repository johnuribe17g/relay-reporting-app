"""Domain value types. Frozen dataclasses; T3 maps them to API models."""

from dataclasses import dataclass
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
