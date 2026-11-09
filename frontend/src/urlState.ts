// Pure URL state (plans/T4-frontend.md §1c). The account never goes into a request except as the header.

export interface UrlState {
  account: string | null;
  week: string | null;
  location: string | null;
}

function param(params: URLSearchParams, key: string): string | null {
  const value = params.get(key);
  return value === null || value === "" ? null : value;
}

export function parseUrl(search: string): UrlState {
  const params = new URLSearchParams(search);
  return {
    account: param(params, "account"),
    week: param(params, "week"),
    location: param(params, "location"),
  };
}

/** The query string for a state: `?account=..&week=..&location=..`, nulls omitted, `""` when empty. */
export function buildUrl(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.account !== null) params.set("account", state.account);
  if (state.week !== null) params.set("week", state.week);
  if (state.location !== null) params.set("location", state.location);
  const query = params.toString();
  return query === "" ? "" : `?${query}`;
}

/** Changing account resets week (its default is unknown until /api/weeks answers) and location. */
export function nextOnAccount(_state: UrlState, account: string): UrlState {
  return { account, week: null, location: null };
}

export function nextOnWeek(state: UrlState, week: string): UrlState {
  return { ...state, week };
}

export function nextOnLocation(state: UrlState, location: string): UrlState {
  return { ...state, location };
}
