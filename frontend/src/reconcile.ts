// Pure reconciliation of URL values against what the API returned (plans/T4-frontend.md §1c, D-27).
// Three stages, because each needs data that only arrives after the previous one.

import type { AccountOut, LocationRow, WeeksOut } from "./api/types";

export type AccountResult =
  | { kind: "default" }
  | { kind: "ok"; id: string }
  | { kind: "error"; code: "unknown_account"; message: string };

/** No param: header-less bootstrap. A param is valid only if it equals String(id) of a listed account. */
export function reconcileAccount(urlAccount: string | null, accounts: AccountOut[]): AccountResult {
  if (urlAccount === null) return { kind: "default" };
  if (accounts.some((a) => String(a.id) === urlAccount)) return { kind: "ok", id: urlAccount };
  return {
    kind: "error",
    code: "unknown_account",
    message: `Account ${urlAccount} does not exist.`,
  };
}

export interface WeekResult {
  week: string | null;
  /** True when the URL's week differs from `week` and the URL should be rewritten (replaceState). */
  corrected: boolean;
  notice: string | null;
}

export function reconcileWeek(
  urlWeek: string | null,
  weeksOut: Pick<WeeksOut, "weeks" | "default_week">,
): WeekResult {
  const { weeks, default_week } = weeksOut;
  if (weeks.length === 0) {
    // Account without selectable weeks: a stale param is removed, the empty state explains.
    return { week: null, corrected: urlWeek !== null, notice: null };
  }
  if (urlWeek === null) return { week: default_week, corrected: true, notice: null };
  if (weeks.includes(urlWeek)) return { week: urlWeek, corrected: false, notice: null };
  return {
    week: default_week,
    corrected: true,
    notice: `Week ${urlWeek} is not available for this account; showing ${default_week ?? "none"}.`,
  };
}

export interface LocationResult {
  location: string | null;
  corrected: boolean;
}

/** Exact match against the report's rows (no case folding, D-06); otherwise dropped. */
export function reconcileLocation(
  urlLocation: string | null,
  report: { locations: Pick<LocationRow, "location">[] },
): LocationResult {
  if (urlLocation === null) return { location: null, corrected: false };
  if (report.locations.some((l) => l.location === urlLocation)) {
    return { location: urlLocation, corrected: false };
  }
  return { location: null, corrected: true };
}
