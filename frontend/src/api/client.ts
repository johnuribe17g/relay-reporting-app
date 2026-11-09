// Typed fetch client (plans/T4-frontend.md §1b). The account goes out only as the X-Account-Id header.

import type { AccountOut, History, Report, SummaryOut, WeeksOut } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function isErrorBody(body: unknown): body is { error: { code: string; message: string } } {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error = (body as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

async function request<T>(
  path: string,
  account: string | null,
  signal?: AbortSignal,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (account !== null) headers["X-Account-Id"] = account;
  const init: RequestInit = { headers, signal };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.method = "POST";
    init.body = JSON.stringify(body);
  }

  // An abort is decided by the signal, never by the error's type or reason (realm-fragile, and
  // abort(reason) can carry anything): if the signal is aborted, the original error goes up untouched.
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "network_error", "Could not reach the API.");
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch (error) {
      if (signal?.aborted) throw error;
    }
    if (isErrorBody(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message);
    }
    throw new ApiError(
      response.status,
      "unexpected_response",
      `Unexpected response (HTTP ${response.status}).`,
    );
  }

  try {
    return (await response.json()) as T;
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(
      response.status,
      "unexpected_response",
      `Unexpected response (HTTP ${response.status}): the body is not JSON.`,
    );
  }
}

/** Never sends the account header: the one endpoint that is not account-scoped (D-22). */
export function getAccounts(signal?: AbortSignal): Promise<AccountOut[]> {
  return request<AccountOut[]>("/api/accounts", null, signal);
}

/** `account` null = header-less bootstrap (the server's demo account answers). */
export function getWeeks(account: string | null, signal?: AbortSignal): Promise<WeeksOut> {
  return request<WeeksOut>("/api/weeks", account, signal);
}

export function getReport(
  account: string,
  week: string | null,
  signal?: AbortSignal,
): Promise<Report> {
  const query = week === null ? "" : `?week=${encodeURIComponent(week)}`;
  return request<Report>(`/api/report${query}`, account, signal);
}

export function getHistory(
  account: string,
  location: string,
  week: string,
  signal?: AbortSignal,
): Promise<History> {
  const path = `/api/locations/${encodeURIComponent(location)}/history?week=${encodeURIComponent(week)}`;
  return request<History>(path, account, signal);
}

/** POST /api/summary. `week` null asks for the default week. Always sends the account header. */
export function postSummary(
  account: string,
  week: string | null,
  signal?: AbortSignal,
): Promise<SummaryOut> {
  return request<SummaryOut>("/api/summary", account, signal, { week });
}
