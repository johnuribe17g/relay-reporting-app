import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import App from "./App";
import a15Weeks from "./test/fixtures/a15-weeks.json";
import a6Report0601 from "./test/fixtures/a6-report-0601.json";
import errInvalidWeek from "./test/fixtures/err-invalid-week.json";
import { held, installFetch, json, type MockFetch } from "./test/mockFetch";

const A1_SEARCH = "?account=15&week=2026-07-20&location=Site+C";

// A push, not a replace: an earlier test's history.back() leaves a forward entry, and the next push
// would truncate it, making history.length comparisons meaningless. Pushing here drops it first.
function open(search: string): void {
  window.history.pushState(null, "", `/${search}`);
}
// The switcher's own label; /^account/i would also match the "Account summary" region.
const accountSelect = (): HTMLSelectElement => screen.getByLabelText(/^account \(demo/i);
const weekSelect = (): HTMLSelectElement => screen.getByLabelText(/^week$/i);
const search = (): string => window.location.search;

function expectOnly(mock: MockFetch, account: string | null, paths: string[]): void {
  expect(mock.paths()).toEqual(paths);
  expect(mock.calls.every((c) => c.account === account)).toBe(true);
}

describe("App: URL state and the request waterfall (plan §2e)", () => {
  test("A1 a reload restores account, week and location with the right requests", async () => {
    const mock = installFetch();
    open(A1_SEARCH);
    render(<App />);

    await screen.findByRole("heading", { name: "Site C" });

    expect(mock.calls).toHaveLength(4);
    const p = mock.paths();
    const at = (path: string): number => p.indexOf(path);
    expect(at("/api/accounts")).toBeGreaterThanOrEqual(0);
    // The URL names an account: weeks waits for /api/accounts (reconcileAccount), then report, then history.
    expect(at("/api/accounts")).toBeLessThan(at("/api/weeks"));
    expect(at("/api/weeks")).toBeLessThan(at("/api/report?week=2026-07-20"));
    expect(at("/api/report?week=2026-07-20")).toBeLessThan(
      at("/api/locations/Site%20C/history?week=2026-07-20"),
    );
    for (const call of mock.calls) {
      expect(call.account).toBe(call.path === "/api/accounts" ? null : "15");
    }
    expect(search()).toBe(A1_SEARCH);
    expect(accountSelect()).toHaveValue("15");
    expect(weekSelect()).toHaveValue("2026-07-20");
    expect(screen.getByText("Week of 2026-07-20")).toBeInTheDocument();
    expect(mock.unmatched).toEqual([]);
  });

  test("A2 with no account the first weeks call has no header and the account is adopted", async () => {
    const mock = installFetch();
    open("");
    const before = window.history.length;
    render(<App />);

    await screen.findByText("Week of 2026-07-20");

    const weeks = mock.calls.filter((c) => c.path === "/api/weeks");
    expect(weeks).toHaveLength(1);
    expect(weeks[0]?.account).toBeNull();
    expect(mock.paths()).toContain("/api/accounts");
    const firstWeeks = mock.calls.indexOf(weeks[0]!);
    mock.calls.slice(firstWeeks + 1).forEach((c) => expect(c.account).toBe("15"));
    expect(mock.calls.filter((c) => c.path.startsWith("/api/report"))).toHaveLength(1);
    expect(mock.paths()).toContain("/api/report?week=2026-07-20");
    expect(search()).toBe("?account=15&week=2026-07-20");
    expect(window.history.length).toBe(before);
    expect(accountSelect()).toHaveValue("15");
    expect(mock.unmatched).toEqual([]);
  });

  test.each(["?account=999", "?account=abc"])(
    "A3 unknown account %s is an error state and no account-scoped request is sent",
    async (query) => {
      const mock = installFetch();
      open(query);
      render(<App />);

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("unknown_account");
      expect(accountSelect()).toBeInTheDocument();
      expectOnly(mock, null, ["/api/accounts"]);
      expect(search()).toBe(query);
    },
  );

  test.each(["?account=15&week=2026-01-05", "?account=15&week=abc", "?account=15&week=2026-07-21"])(
    "A4 stale week %s falls back to the default with a notice, via replaceState",
    async (query) => {
      const mock = installFetch();
      open(query);
      const before = window.history.length;
      render(<App />);

      const notice = await screen.findByRole("status");
      const stale = query.split("week=")[1] ?? "";
      expect(notice).toHaveTextContent(stale);
      expect(notice).toHaveTextContent("2026-07-20");
      await screen.findByText("Week of 2026-07-20");
      expect(search()).toBe("?account=15&week=2026-07-20");
      expect(window.history.length).toBe(before);
      expect(mock.paths()).toContain("/api/report?week=2026-07-20");
      expect(mock.paths().filter((path) => path.includes(stale))).toEqual([]);
      expect(mock.unmatched).toEqual([]);
    },
  );

  test("A5 a location that is not in the report is dropped and no history is requested", async () => {
    const mock = installFetch();
    open("?account=15&week=2026-07-20&location=Nope");
    render(<App />);

    await screen.findByText("Select a location to see its history.");
    await waitFor(() => expect(search()).toBe("?account=15&week=2026-07-20"));
    expect(mock.paths().some((path) => path.includes("/history"))).toBe(false);
  });

  test("A6 account 20: report without a week, stale week removed, empty state, week selector disabled", async () => {
    const mock = installFetch();
    open("?account=20&week=2026-03-30");
    render(<App />);

    await screen.findByText(/no activity yet/i);
    expect(mock.paths()).toContain("/api/report");
    expect(mock.paths().some((path) => path.includes("week="))).toBe(false);
    expect(search()).toBe("?account=20");
    expect(weekSelect()).toBeDisabled();
    expect(mock.unmatched).toEqual([]);
  });

  test("A7 switching account pushes one history entry and back restores the previous view", async () => {
    const mock = installFetch();
    open(A1_SEARCH);
    const before = window.history.length;
    render(<App />);
    await screen.findByRole("heading", { name: "Site C" });

    await userEvent.setup().selectOptions(accountSelect(), "6");

    await waitFor(() => expect(search()).toBe("?account=6&week=2026-07-20"));
    expect(window.history.length).toBe(before + 1);
    await screen.findByRole("button", { name: "Site M" });
    expect(screen.getByText("Select a location to see its history.")).toBeInTheDocument();
    const weeks6 = mock.calls.filter((c) => c.path === "/api/weeks" && c.account === "6");
    expect(weeks6).toHaveLength(1);
    expect(mock.paths()).toContain("/api/report?week=2026-07-20");
    expect(mock.calls.filter((c) => c.path.includes("/history"))).toHaveLength(1);

    act(() => window.history.back());

    await waitFor(() => expect(search()).toBe(A1_SEARCH));
    await screen.findByRole("heading", { name: "Site C" });
    expect(accountSelect()).toHaveValue("15");
    expect(mock.unmatched).toEqual([]);
  });

  test("A8 a week change is a push and keeps the location when the new report has it", async () => {
    const mock = installFetch();
    open("?account=6&week=2026-07-20&location=Site+G");
    render(<App />);
    await screen.findByRole("heading", { name: "Site G" });
    const before = window.history.length;

    await userEvent.setup().selectOptions(weekSelect(), "2026-06-01");

    await waitFor(() => expect(search()).toBe("?account=6&week=2026-06-01&location=Site+G"));
    expect(window.history.length).toBe(before + 1);
    await waitFor(() =>
      expect(mock.paths()).toContain("/api/locations/Site%20G/history?week=2026-06-01"),
    );
    await screen.findByRole("heading", { name: "Site G" });
  });

  test("A8 a week change drops a location the new report does not have, by replaceState", async () => {
    const without = structuredClone(a6Report0601);
    without.locations = without.locations.filter((l) => l.location !== "Site G");
    const mock = installFetch([
      ({ path, account }) =>
        account === "6" && path === "/api/report?week=2026-06-01" ? json(without) : undefined,
    ]);
    open("?account=6&week=2026-07-20&location=Site+G");
    render(<App />);
    await screen.findByRole("heading", { name: "Site G" });
    const before = window.history.length;

    await userEvent.setup().selectOptions(weekSelect(), "2026-06-01");

    await waitFor(() => expect(search()).toBe("?account=6&week=2026-06-01"));
    await screen.findByText("Select a location to see its history.");
    expect(window.history.length).toBe(before + 1);
    expect(mock.paths()).not.toContain("/api/locations/Site%20G/history?week=2026-06-01");
  });

  test.each([true, false])(
    "A9 a late response for a superseded account is ignored and shows no error (abort honored: %s)",
    async (honorAbort) => {
      const slow = held(honorAbort);
      const mock = installFetch([
        (call) => (call.path === "/api/weeks" && call.account === "15" ? slow.handler(call) : undefined),
      ]);
      open("?account=15&week=2026-07-20");
      render(<App />);
      await waitFor(() => expect(mock.paths()).toContain("/api/weeks")); // account 15's weeks is pending

      await userEvent.setup().selectOptions(accountSelect(), "6");
      await screen.findByRole("button", { name: "Site M" }); // account 6 is fully shown

      await act(async () => {
        slow.release(json(a15Weeks)); // the superseded request answers late
        await new Promise((resolve) => setTimeout(resolve, 20));
      });

      // Account 6 has 15 locations (data profile §1); account 15's stale answer would show 3.
      expect(screen.getAllByRole("button")).toHaveLength(15);
      expect(screen.getByRole("button", { name: "Site M" })).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(accountSelect()).toHaveValue("6");
    },
  );

  test("A10 a pending report shows the loading text, then the API's error shape", async () => {
    let respond!: (response: Response) => void;
    installFetch([
      ({ path }) =>
        path.startsWith("/api/report")
          ? new Promise<Response>((resolve) => {
              respond = resolve;
            })
          : undefined,
    ]);
    open("?account=15&week=2026-07-20");
    render(<App />);
    await waitFor(() => expect(respond).toBeDefined());
    expect(screen.getByText("Loading…")).toBeInTheDocument();

    await act(async () => {
      respond(json(errInvalidWeek, 422));
    });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("invalid_week");
    expect(alert).toHaveTextContent(
      "week must be a Monday in the selectable range 2026-03-30 .. 2026-07-20",
    );
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  });

  test("A10 a network failure shows a network_error message", async () => {
    installFetch([
      ({ path }) =>
        path.startsWith("/api/report") ? Promise.reject(new TypeError("Failed to fetch")) : undefined,
    ]);
    open("?account=15&week=2026-07-20");
    render(<App />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("network_error");
    expect(alert).toHaveTextContent("Could not reach the API.");
  });
});
