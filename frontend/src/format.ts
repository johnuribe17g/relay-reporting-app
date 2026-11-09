// Render-time formatting and copy (plans/T4-frontend.md §1d). Floats are formatted only here, and nothing
// here computes a statistic. `en-US` is fixed so output does not depend on the machine; a negative sign is
// U+2212; negative zero is never shown.
import type { BaselineOut, Parameters, Summary, SummaryOut, Verdict } from "./api/types";

const MINUS = "−";
const EMPTY = "—";

const plain = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, signDisplay: "negative" });
const twoDecimals = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "negative",
});
const signed = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, signDisplay: "exceptZero" });

const withMinus = (text: string): string => text.replace("-", MINUS);

/** At most 1 decimal: `5.5`, `19`, `880`. */
export function fmtNum(n: number | null): string {
  return n === null ? EMPTY : withMinus(plain.format(n));
}

/** The score `z` with 2 decimals: `2.77`, `−1.21`. */
export function fmtZ(z: number | null): string {
  return z === null ? EMPTY : withMinus(twoDecimals.format(z));
}

/** A signed difference with at most 1 decimal: `+6.5`, `−4.5`, `0`. */
export function fmtDiff(diff: number | null): string {
  return diff === null ? EMPTY : withMinus(signed.format(diff));
}

/**
 * The band as it is shown: the low edge is clipped at 0 here, never in the data (a count cannot be
 * negative). The one function used by both the text and, later, the chart.
 */
export function displayBand(band: Pick<BaselineOut, "band_low" | "band_high">): {
  low: number;
  high: number;
} {
  return { low: Math.max(0, band.band_low), high: band.band_high };
}

export function fmtBand(band: Pick<BaselineOut, "band_low" | "band_high">): string {
  const { low, high } = displayBand(band);
  return `${fmtNum(low)} to ${fmtNum(high)}`;
}

/** `2026-07-27T22:20:34Z` -> `2026-07-27 22:20 UTC`, read from the string (no Date, no time zone shift). */
export function fmtAsOf(asOf: string | null): string {
  if (asOf === null) return EMPTY;
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(asOf);
  return match === null ? asOf : `${match[1]} ${match[2]} UTC`;
}

/** The N comes from the API (`baseline.weeks_used`), never from a constant. */
export function baselineSentence(weeksUsed: number): string {
  return `compared with the last ${weeksUsed} week${weeksUsed === 1 ? "" : "s"}`;
}

const LABELS: Record<Verdict, string> = {
  normal: "Normal",
  higher: "Higher than usual",
  lower: "Lower than usual",
  too_quiet: "Too quiet to judge",
  not_enough_history: "Not enough history",
  no_activity: "No activity",
};

export function verdictLabel(verdict: Verdict): string {
  return LABELS[verdict];
}

/** Why a verdict is not a judgement, from the API's numbers; `null` for a judged verdict. */
export function reasonText(
  summary: Pick<Summary, "verdict" | "history_weeks" | "baseline">,
  parameters: Parameters,
): string | null {
  switch (summary.verdict) {
    case "too_quiet":
      return `Too quiet to judge: normal is ${fmtNum(summary.baseline?.median ?? null)} events a week, below ${fmtNum(parameters.min_baseline_median)}.`;
    case "not_enough_history":
      return `Not enough history: ${summary.history_weeks} of ${parameters.min_history_weeks} weeks.`;
    case "no_activity":
      return "No activity.";
    default:
      return null;
  }
}

/** A parameter as written in the copy: `2`, `2.5`, `12` (no rounding, so the text always matches the setting). */
const param = (value: number): string => String(value);

export interface Glossary {
  median: string;
  range: string;
  z: string;
  diff: string;
  tooQuiet: string;
  notEnoughHistory: string;
}

/**
 * One-line definitions of the numbers on the screen. Every number in them comes from `report.parameters`,
 * never from a literal (plans/T4-frontend.md §4, CP3c). Shown in the glossary and as the table headers' title.
 */
export function glossary(parameters: Parameters): Glossary {
  return {
    median: `The middle value of the weekly totals over up to the last ${param(parameters.baseline_weeks)} weeks: half the weeks were above it, half below.`,
    range:
      "Totals inside it count as normal; a total at an edge or outside it is flagged. It comes from the median and how much the weeks usually vary.",
    z: `How unusual this week is, in units of typical week-to-week variation. 0 is exactly normal; a week is flagged from \u00b1${param(parameters.z_min)}, and only if the difference is at least ${param(parameters.min_abs)} events.`,
    diff: "This week's total minus the median.",
    tooQuiet: `The normal week has fewer than ${param(parameters.min_baseline_median)} events, too few to judge a quiet week.`,
    notEnoughHistory: `Fewer than ${param(parameters.min_history_weeks)} weeks of data, too few to judge.`,
  };
}

/** The card's label. A template response never gets the AI wording; mock output is never a model's. */
export function summaryLabel(summary: Pick<SummaryOut, "source" | "reason" | "provider">): string {
  if (summary.source === "ai") {
    return summary.provider === "mock"
      ? "AI summary · preview (mock provider)"
      : "AI summary · preview (anthropic)";
  }
  return summary.reason === null
    ? "Template summary"
    : `Template summary — ${summary.reason.replace(/_/g, " ")}`;
}
