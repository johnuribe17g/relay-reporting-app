// Hand-mirrored from backend/app/schemas.py (plans/T4-frontend.md Q1). Dates and `as_of` stay strings.
export type Verdict =
  | "normal"
  | "higher"
  | "lower"
  | "not_enough_history"
  | "too_quiet"
  | "no_activity";

export interface AccountOut {
  id: number;
  name: string;
  timezone: string;
}

export interface Parameters {
  baseline_weeks: number;
  min_history_weeks: number;
  z_min: number;
  min_abs: number;
  min_baseline_median: number;
}

export interface ByType {
  call_received: number;
  lead_created: number;
  appointment_set: number;
}

export interface BaselineOut {
  median: number;
  mad: number;
  spread: number;
  weeks_used: number;
  band_low: number;
  band_high: number;
}

export interface DataQuality {
  unknown_events_in_window: number;
}

export interface Summary {
  total: number | null;
  verdict: Verdict;
  z: number | null;
  diff: number | null;
  history_weeks: number;
  baseline: BaselineOut | null;
  by_type: ByType | null;
  data_quality: DataQuality;
}

export interface LocationRow extends Summary {
  location: string;
}

export interface Report {
  account: AccountOut;
  week: string | null;
  as_of: string | null;
  parameters: Parameters;
  account_summary: Summary;
  locations: LocationRow[];
}

export interface WeeksOut {
  account: AccountOut;
  weeks: string[];
  default_week: string | null;
  as_of: string | null;
}

export interface WeekPoint {
  week: string;
  total: number;
  by_type: ByType;
  role: "baseline" | "selected";
}

export interface History {
  account: AccountOut;
  location: string;
  week: string;
  as_of: string | null;
  parameters: Parameters;
  verdict: Verdict;
  z: number | null;
  diff: number | null;
  baseline: BaselineOut | null;
  weeks: WeekPoint[];
  data_quality: DataQuality;
}

export type SummaryReason =
  | "disabled"
  | "nothing_to_summarize"
  | "provider_error"
  | "timeout"
  | "validation_failed";

export interface SummaryOut {
  week: string | null;
  /** Set only when `source` is "ai". */
  headline: string | null;
  /** The server-rendered fact lines, one per line. */
  text: string;
  source: "ai" | "template";
  reason: SummaryReason | null;
  provider: "mock" | "anthropic";
  prompt_version: string;
}
