"""Response models (plans/T3-backend-api.md §1b). Floats are returned unrounded."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.models import Verdict


class AccountOut(BaseModel):
    id: int
    name: str
    timezone: str


class Parameters(BaseModel):
    baseline_weeks: int
    min_history_weeks: int
    z_min: float
    min_abs: float
    min_baseline_median: float


class ByType(BaseModel):
    call_received: int
    lead_created: int
    appointment_set: int


class BaselineOut(BaseModel):
    median: float
    mad: float
    spread: float
    weeks_used: int
    band_low: float
    band_high: float


class DataQuality(BaseModel):
    # Sum over the series window (baseline weeks + the selected week), not just the selected week:
    # `total` is the selected week only, so this field is named to say it is not.
    unknown_events_in_window: int


class Summary(BaseModel):
    """Selected-week figures of the account or of one location. `None` fields: not judged."""

    total: int | None
    verdict: Verdict
    z: float | None
    diff: float | None
    history_weeks: int
    baseline: BaselineOut | None
    by_type: ByType | None
    data_quality: DataQuality


class LocationRow(Summary):
    location: str


class Report(BaseModel):
    account: AccountOut
    week: date | None
    as_of: datetime | None
    parameters: Parameters
    account_summary: Summary
    locations: list[LocationRow]


class WeeksOut(BaseModel):
    account: AccountOut
    weeks: list[date]
    default_week: date | None
    as_of: datetime | None


class WeekPoint(BaseModel):
    week: date
    total: int
    by_type: ByType
    role: Literal["baseline", "selected"]


class History(BaseModel):
    account: AccountOut
    location: str
    week: date
    as_of: datetime | None
    parameters: Parameters
    verdict: Verdict
    z: float | None
    diff: float | None
    baseline: BaselineOut | None
    weeks: list[WeekPoint]
    data_quality: DataQuality


SummaryReason = Literal[
    "disabled", "nothing_to_summarize", "provider_error", "timeout", "validation_failed"
]


class SummaryRequest(BaseModel):
    # A string like `/api/report`'s `week`: `resolve_week` raises `invalid_week` (plans/T5 §1a).
    week: str | None = None


class SummaryOut(BaseModel):
    """`text` is the server-rendered fact lines; `headline` is set only when `source` is `ai`."""

    week: date | None
    headline: str | None
    text: str
    source: Literal["ai", "template"]
    reason: SummaryReason | None
    provider: Literal["mock", "anthropic"]
    prompt_version: str
