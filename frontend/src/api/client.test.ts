import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import errAccountNotFound from "../test/fixtures/err-account-not-found.json";
import errInvalidWeek from "../test/fixtures/err-invalid-week.json";
import {
  ApiError,
  getAccounts,
  getHistory,
  getReport,
  getWeeks,
} from "./client";

const fetchMock = vi.fn();

function reply(body: unknown, status = 200): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function lastCall(): { url: string; headers: Record<string, string> } {
  const call = fetchMock.mock.calls.at(-1) as [string, RequestInit | undefined];
  return { url: call[0], headers: (call[1]?.headers ?? {}) as Record<string, string> };
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => Promise.resolve(reply({})));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("client (plan §2d)", () => {
  test("K1 getAccounts never sends the account header", async () => {
    await getAccounts();
    const { url, headers } = lastCall();
    expect(url).toBe("/api/accounts");
    expect(headers).not.toHaveProperty("X-Account-Id");
  });

  test("K2 getWeeks sends the header only when an account is given", async () => {
    await getWeeks(null);
    expect(lastCall().url).toBe("/api/weeks");
    expect(lastCall().headers).not.toHaveProperty("X-Account-Id");

    await getWeeks("15");
    expect(lastCall().url).toBe("/api/weeks");
    expect(lastCall().headers["X-Account-Id"]).toBe("15");
  });

  test("K3 getReport sends the header and the week only when given", async () => {
    await getReport("15", null);
    expect(lastCall().url).toBe("/api/report");
    expect(lastCall().headers["X-Account-Id"]).toBe("15");

    await getReport("15", "2026-07-20");
    expect(lastCall().url).toBe("/api/report?week=2026-07-20");
    expect(lastCall().headers["X-Account-Id"]).toBe("15");
  });

  test("K4 getHistory encodes the space in the location", async () => {
    await getHistory("15", "Site C", "2026-07-20");
    expect(lastCall().url).toBe("/api/locations/Site%20C/history?week=2026-07-20");
    expect(lastCall().headers["X-Account-Id"]).toBe("15");
  });

  test("K5 getHistory encodes a slash in the location", async () => {
    await getHistory("15", "A/B", "2026-07-20");
    expect(lastCall().url).toBe("/api/locations/A%2FB/history?week=2026-07-20");
  });

  test("K6 the one error shape becomes an ApiError with its code and message", async () => {
    fetchMock.mockResolvedValueOnce(reply(errAccountNotFound, 404));
    const notFound = await getWeeks("999").catch((e: unknown) => e);
    expect(notFound).toBeInstanceOf(ApiError);
    expect((notFound as ApiError).status).toBe(404);
    expect((notFound as ApiError).code).toBe("account_not_found");
    expect((notFound as ApiError).message).toBe(errAccountNotFound.error.message);

    fetchMock.mockResolvedValueOnce(reply(errInvalidWeek, 422));
    const invalid = await getReport("15", "2026-01-05").catch((e: unknown) => e);
    expect((invalid as ApiError).status).toBe(422);
    expect((invalid as ApiError).code).toBe("invalid_week");
    expect((invalid as ApiError).message).toBe(errInvalidWeek.error.message);
  });

  test("K7 a non-JSON error (the proxy's 502) is an unexpected_response", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("<html>Bad Gateway</html>", { status: 502, headers: { "content-type": "text/html" } }),
    );
    const err = await getAccounts().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(502);
    expect((err as ApiError).code).toBe("unexpected_response");
    expect((err as ApiError).message).toContain("502");
  });

  test("K8 a rejected fetch is a network_error; an abort is rethrown untouched", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const net = await getAccounts().catch((e: unknown) => e);
    expect(net).toBeInstanceOf(ApiError);
    expect((net as ApiError).code).toBe("network_error");

    const abort = new DOMException("aborted", "AbortError");
    fetchMock.mockRejectedValueOnce(abort);
    const err = await getAccounts().catch((e: unknown) => e);
    expect(err).toBe(abort);
  });
});
