// A small router standing in for the API, installed as the global `fetch` (plans/T4-frontend.md Q2):
// the real client runs, so the header, the paths and the error mapping are exercised.
import { vi } from "vitest";

import a15History from "./fixtures/a15-history-siteC-0720.json";
import a15Report from "./fixtures/a15-report-0720.json";
import a15Weeks from "./fixtures/a15-weeks.json";
import a20Report from "./fixtures/a20-report.json";
import a20Weeks from "./fixtures/a20-weeks.json";
import a6HistorySiteG from "./fixtures/a6-history-siteG-0601.json";
import a6Report0601 from "./fixtures/a6-report-0601.json";
import a6Report0720 from "./fixtures/a6-report-0720.json";
import a6Weeks from "./fixtures/a6-weeks.json";
import accounts from "./fixtures/accounts.json";
import errAccountNotFound from "./fixtures/err-account-not-found.json";

export interface Call {
  path: string;
  /** The X-Account-Id header, or null when it was not sent. */
  account: string | null;
  signal: AbortSignal | undefined;
}

/** Return a Response (or a promise of one) to answer, or undefined to pass to the next handler. */
export type Handler = (call: Call) => Response | Promise<Response> | undefined;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const fixtures: Record<string, unknown> = {
  "|/api/accounts": accounts,
  // No header: the server's demo account (15, D-22) answers.
  "|/api/weeks": a15Weeks,
  "15|/api/weeks": a15Weeks,
  "6|/api/weeks": a6Weeks,
  "20|/api/weeks": a20Weeks,
  "15|/api/report?week=2026-07-20": a15Report,
  "6|/api/report?week=2026-07-20": a6Report0720,
  "6|/api/report?week=2026-06-01": a6Report0601,
  "20|/api/report": a20Report,
  "15|/api/locations/Site%20C/history?week=2026-07-20": a15History,
};

function defaultHandler({ path, account }: Call): Response | undefined {
  const key = `${account ?? ""}|${path}`;
  if (key in fixtures) return json(fixtures[key]);
  if (account === "999" && path === "/api/weeks") return json(errAccountNotFound, 404);
  // Stand-in body for any week of account 6's Site G (only the request is asserted by the tests).
  if (account === "6" && path.startsWith("/api/locations/Site%20G/history?week=")) {
    return json(a6HistorySiteG);
  }
  return undefined;
}

export interface MockFetch {
  calls: Call[];
  unmatched: Call[];
  paths: () => string[];
}

export function installFetch(extra: Handler[] = []): MockFetch {
  const calls: Call[] = [];
  const unmatched: Call[] = [];
  vi.stubGlobal(
    "fetch",
    (path: string, init?: RequestInit): Promise<Response> => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const call: Call = {
        path,
        account: headers["X-Account-Id"] ?? null,
        signal: init?.signal ?? undefined,
      };
      calls.push(call);
      for (const handler of [...extra, defaultHandler]) {
        const response = handler(call);
        if (response !== undefined) return Promise.resolve(response);
      }
      unmatched.push(call);
      return Promise.resolve(json({ error: { code: "test_unmatched", message: path } }, 500));
    },
  );
  return { calls, unmatched, paths: () => calls.map((c) => c.path) };
}

/** A response the test releases later; like the real fetch it rejects with the signal's reason on abort. */
export function held(honorAbort: boolean): {
  handler: (call: Call) => Promise<Response>;
  release: (response: Response) => void;
} {
  let release!: (response: Response) => void;
  const handler = (call: Call): Promise<Response> =>
    new Promise<Response>((resolve, reject) => {
      release = resolve;
      if (honorAbort) {
        call.signal?.addEventListener("abort", () => reject(call.signal?.reason));
      }
    });
  return { handler, release: (response) => release(response) };
}
