import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import App from "./App";
import type { History, LocationRow, Report, Verdict } from "./api/types";
import { AccountSummary } from "./components/AccountSummary";
import { LocationDetail } from "./components/LocationDetail";
import { LocationTable } from "./components/LocationTable";
import a15History from "./test/fixtures/a15-history-siteC-0720.json";
import a15Report from "./test/fixtures/a15-report-0720.json";
import a20Report from "./test/fixtures/a20-report.json";
import a6HistorySiteG from "./test/fixtures/a6-history-siteG-0601.json";
import a6Report0601 from "./test/fixtures/a6-report-0601.json";
import a6Report0720 from "./test/fixtures/a6-report-0720.json";
import errAccountNotFound from "./test/fixtures/err-account-not-found.json";
import { installFetch, json } from "./test/mockFetch";

// Fixtures are real API output; clones are mutated by one field inside the test, never stored.
const clone = (fixture: unknown): Report => structuredClone(fixture) as Report;

function valueOf(region: HTMLElement, label: string): string {
  const dt = within(region).getByText(label, { selector: "dt" });
  return dt.nextElementSibling?.textContent ?? "";
}

function rows(): HTMLElement[] {
  return screen.getAllByRole("row").slice(1); // drop the header row
}

function cells(row: HTMLElement): string[] {
  return within(row).getAllByRole("cell").map((c) => c.textContent ?? "");
}

function table(report: Report): void {
  render(
    <LocationTable
      locations={report.locations}
      parameters={report.parameters}
      selected={null}
      onSelect={() => undefined}
    />,
  );
}

describe("account summary and location table (plan §2f)", () => {
  test("R1 account 15 at 2026-07-20: a normal week", () => {
    // median 19, MAD 4, spread max(1.4826*4 = 5.9304, sqrt(19) = 4.359, 1) = 5.9304, z = 1/5.9304 = 0.1686,
    // h = max(2*5.9304 = 11.8608, 3): band 7.1392 .. 30.8608
    render(<AccountSummary report={clone(a15Report)} />);
    const region = screen.getByRole("region", { name: "Account summary" });
    expect(region).toHaveAttribute("data-verdict", "normal");
    expect(within(region).getByText("Normal", { selector: "strong" })).toBeInTheDocument();
    expect(valueOf(region, "Events this week")).toBe("20");
    expect(valueOf(region, "Normal (median)")).toBe("19");
    expect(valueOf(region, "Normal range")).toContain("7.1 to 30.9");
    expect(valueOf(region, "Score (z)")).toBe("0.17");
    expect(screen.getByText("Week of 2026-07-20")).toBeInTheDocument();
  });

  test("R2 account 15: Site C is the first row, higher than usual", () => {
    // Site C: total 12, median 5.5, spread sqrt(5.5) = 2.3452, z = 6.5/2.3452 = 2.7716, diff 6.5,
    // h = 2*2.3452 = 4.6904: band 0.8096 .. 10.1904
    table(clone(a15Report));
    const first = rows()[0] as HTMLElement;
    expect(first).toHaveAttribute("data-verdict", "higher");
    expect(within(first).getByRole("button", { name: "Site C" })).toBeInTheDocument();
    const [, verdict, total, normal, range, z, diff] = cells(first);
    expect(verdict).toContain("Higher than usual");
    expect([total, normal, range, z, diff]).toEqual(["12", "5.5", "0.8 to 10.2", "2.77", "+6.5"]);
  });

  test("R3 account 6 at 2026-06-01: the spike", () => {
    // median 73.5, MAD 9, spread 13.3434, z = 806.5/13.3434 = 60.44, h = 26.6868: band 46.8132 .. 100.1868
    render(<AccountSummary report={clone(a6Report0601)} />);
    const region = screen.getByRole("region", { name: "Account summary" });
    expect(region).toHaveAttribute("data-verdict", "higher");
    expect(valueOf(region, "Events this week")).toBe("880");
    expect(valueOf(region, "Normal (median)")).toBe("73.5");
    expect(valueOf(region, "Normal range")).toContain("46.8 to 100.2");
    expect(valueOf(region, "Score (z)")).toBe("60.44");
  });

  test("R4 rows are rendered in exactly the order the API gave", () => {
    // [Site B, an unjudged row, Site C, Site A]: not by |z| (B before C), not by name asc (B, U, C, A),
    // not by name desc (U, C, B, A), not unjudged-last.
    const report = clone(a15Report);
    const byName = (name: string): LocationRow => {
      const row = report.locations.find((l) => l.location === name);
      if (row === undefined) throw new Error(`fixture has no ${name}`);
      return row;
    };
    const unjudged: LocationRow = {
      ...byName("Site A"),
      location: "Site U",
      verdict: "too_quiet",
      z: null,
      diff: null,
    };
    report.locations = [byName("Site B"), unjudged, byName("Site C"), byName("Site A")];
    table(report);
    const names = rows().map((r) => within(r).getByRole("button").textContent);
    expect(names).toEqual(["Site B", "Site U", "Site C", "Site A"]);
  });

  test("R5 a too_quiet row shows its reason from the baseline and the parameters", () => {
    // account 6 Site M at 2026-07-20: median 3.5 < min_baseline_median 4 (T3 S11)
    table(clone(a6Report0720));
    const row = screen.getByRole("button", { name: "Site M" }).closest("tr") as HTMLElement;
    expect(row).toHaveAttribute("data-verdict", "too_quiet");
    const [, verdict, , , , z] = cells(row);
    expect(verdict).toContain("3.5");
    expect(verdict).toContain("below 4");
    expect(z).toBe("—");
  });

  test("R6 the copy follows the data: changed parameters and weeks_used change the text", () => {
    const report = clone(a6Report0720);
    report.parameters.min_baseline_median = 5;
    if (report.account_summary.baseline === null) throw new Error("fixture has a baseline");
    report.account_summary.baseline.weeks_used = 9;
    render(
      <>
        <AccountSummary report={report} />
        <LocationTable
          locations={report.locations}
          parameters={report.parameters}
          selected={null}
          onSelect={() => undefined}
        />
      </>,
    );
    const text = document.body.textContent ?? "";
    expect(text).toContain("below 5");
    expect(text).toContain("last 9 weeks");
    expect(text).not.toContain("below 4");
    expect(text).not.toContain("last 12 weeks");
  });

  test("R7 a not_enough_history row shows its reason and no band", () => {
    const report = clone(a15Report);
    report.parameters.min_history_weeks = 8;
    const young: LocationRow = {
      ...(report.locations[0] as LocationRow),
      location: "Site Y",
      verdict: "not_enough_history",
      history_weeks: 5,
      z: null,
      diff: null,
      baseline: null,
    };
    report.locations = [young];
    table(report);
    const [, verdict, , normal, range, z] = cells(rows()[0] as HTMLElement);
    expect(verdict).toContain("5 of 8 weeks");
    expect([normal, range, z]).toEqual(["—", "—", "—"]);
  });

  test("R8 each location verdict has its own text; account empty states differ", async () => {
    const report = clone(a15Report);
    const base = report.locations[0] as LocationRow;
    const verdicts: Verdict[] = ["normal", "higher", "lower", "too_quiet"];
    report.locations = verdicts.map((verdict) => ({ ...base, location: `Site ${verdict}`, verdict }));
    table(report);
    const labels = rows().map((r) => cells(r)[1] ?? "");
    expect(labels[0]).toContain("Normal");
    expect(labels[1]).toContain("Higher than usual");
    expect(labels[2]).toContain("Lower than usual");
    expect(labels[3]).toContain("Too quiet to judge");
    expect(new Set(labels).size).toBe(4);
  });

  test("R8 no_activity and an account-level not_enough_history are different states", async () => {
    installFetch();
    window.history.pushState(null, "", "/?account=20");
    const { unmount } = render(<App />);
    await screen.findByText(/no activity yet/i);
    expect(screen.queryByText(/not enough history yet/i)).not.toBeInTheDocument();
    unmount();

    const young = clone(a20Report);
    young.account_summary.verdict = "not_enough_history";
    installFetch([
      ({ path, account }) => (account === "20" && path === "/api/report" ? json(young) : undefined),
    ]);
    window.history.pushState(null, "", "/?account=20");
    render(<App />);
    await screen.findByText(/not enough history yet/i);
    expect(screen.queryByText(/no activity yet/i)).not.toBeInTheDocument();
  });

  test("R9 the data-quality warning shows only when unknown events exist, worded as the window", () => {
    const report = clone(a15Report);
    const { unmount } = render(<AccountSummary report={report} />);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    unmount();

    report.account_summary.data_quality.unknown_events_in_window = 3;
    render(<AccountSummary report={report} />);
    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("3");
    expect(note).toHaveTextContent("baseline window");
  });

  test("R12 clicking a location pushes the URL and marks the row as current", async () => {
    installFetch();
    window.history.pushState(null, "", "/?account=15&week=2026-07-20");
    render(<App />);
    const button = await screen.findByRole("button", { name: "Site A" });
    const before = window.history.length;

    await userEvent.setup().click(button);

    await waitFor(() =>
      expect(window.location.search).toBe("?account=15&week=2026-07-20&location=Site+A"),
    );
    expect(window.history.length).toBe(before + 1);
    expect(screen.getByRole("button", { name: "Site A" })).toHaveAttribute("aria-current", "true");
  });
});

const cloneHistory = (fixture: unknown): History => structuredClone(fixture) as History;

function detail(history: History, historyWeeks = 12): HTMLElement {
  render(
    <LocationDetail
      location={history.location}
      historyWeeks={historyWeeks}
      history={{ status: "ok", data: history }}
    />,
  );
  return screen.getByRole("region", { name: "Location detail" });
}

describe("location detail (plan §2f, CP3a)", () => {
  test("R9 at location level the data-quality warning shows only when unknown events exist", () => {
    const history = cloneHistory(a15History);
    const { unmount } = render(
      <LocationDetail location="Site C" historyWeeks={12} history={{ status: "ok", data: history }} />,
    );
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    unmount();

    history.data_quality.unknown_events_in_window = 3;
    render(
      <LocationDetail location="Site C" historyWeeks={12} history={{ status: "ok", data: history }} />,
    );
    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("3");
    expect(note).toHaveTextContent("baseline window");
  });

  test("R10 a band whose low edge is negative is shown clipped at 0", () => {
    // account 6 Site G at 2026-06-01: band_low is -1.4304 (T3 S16), shown as 0
    const region = detail(cloneHistory(a6HistorySiteG));
    expect(valueOf(region, "Normal range")).toMatch(/^0 to \d/);
    expect(document.body.textContent).not.toContain("\u22121.4");
    expect(document.body.textContent).not.toContain("-1.4");
  });

  test("R11 account 15 Site C at 2026-07-20: the weeks table and the selected row", () => {
    // 2026-07-20 - 12 weeks = 84 days = 2026-04-27, on or after the first complete week 2026-02-02, so the
    // window is full: 12 baseline weeks (04-27 .. 07-13) + the selected week = 13 rows. The totals are the
    // hand-computed series of T3 S6: 5,4,4,6,4,5,10,4,6,6,7,6 and x = 12.
    // Site C: median 5.5, z = 6.5/2.3452 = 2.7716, diff 6.5, band 0.8096 .. 10.1904.
    const region = detail(cloneHistory(a15History));
    expect(screen.getByRole("heading", { name: "Site C" })).toBeInTheDocument();
    expect(region).toHaveAttribute("data-verdict", "higher");
    expect(valueOf(region, "This week")).toBe("12");
    expect(valueOf(region, "Normal (median)")).toBe("5.5");
    expect(valueOf(region, "Normal range")).toContain("0.8 to 10.2");
    expect(valueOf(region, "Score (z)")).toBe("2.77");
    expect(valueOf(region, "Difference")).toBe("+6.5");

    const body = within(within(region).getByRole("table", { name: "Weekly totals" }));
    const data = body.getAllByRole("row").slice(1);
    expect(data).toHaveLength(13);
    expect(data.map((r) => cells(r)[0])).toEqual([
      "2026-04-27", "2026-05-04", "2026-05-11", "2026-05-18", "2026-05-25", "2026-06-01", "2026-06-08",
      "2026-06-15", "2026-06-22", "2026-06-29", "2026-07-06", "2026-07-13", "2026-07-20",
    ]);
    expect(data.map((r) => cells(r)[1])).toEqual([
      "5", "4", "4", "6", "4", "5", "10", "4", "6", "6", "7", "6", "12",
    ]);
    expect(data.slice(0, 12).every((r) => cells(r)[5] === "Baseline")).toBe(true);
    const last = data[12] as HTMLElement;
    expect(cells(last)[5]).toBe("Selected week");
    expect(last).toHaveAttribute("data-role", "selected");
    // the chart note of the plan: the band is the selected week's (the caption under the chart)
    expect(region.textContent).toContain(
      "Shaded: normal range for the selected week (0.8 to 10.2). Earlier weeks are shown for context and are not judged against it.",
    );
  });

  test("R13 the chart: 13 points, the selected one is the last, one band, a caption", () => {
    // 13 points: the same window arithmetic as R11 (12 baseline weeks 04-27 .. 07-13 + the selected 07-20).
    // Site C: totals max 12 > band high 10.19, so yMax = 12 and the Y labels are 0 and 12.
    const region = detail(cloneHistory(a15History));
    const svg = within(region).getByRole("img", {
      name: /Site C.*13 weeks.*selected week 2026-07-20 total 12.*normal range 0\.8 to 10\.2/,
    });
    const points = Array.from(svg.querySelectorAll("circle[data-role]"));
    expect(points).toHaveLength(13);
    const selected = points.filter((p) => p.getAttribute("data-role") === "selected");
    expect(selected).toHaveLength(1);
    expect(points[12]).toBe(selected[0]);
    expect(points.slice(0, 12).every((p) => p.getAttribute("data-role") === "baseline")).toBe(true);
    expect(Number(selected[0]?.getAttribute("r"))).toBeGreaterThan(Number(points[0]?.getAttribute("r")));
    expect(svg.querySelectorAll('rect[data-chart="band"]')).toHaveLength(1);
    const labels = Array.from(svg.querySelectorAll("text")).map((t) => t.textContent);
    expect(labels).toEqual(expect.arrayContaining(["0", "12", "2026-04-27", "2026-07-20"]));
    expect(labels.filter((t) => t === "12")).toHaveLength(2); // the Y maximum and the selected total
    expect(within(region).getByRole("table", { name: "Weekly totals" })).toBeInTheDocument();
  });

  test("R15 a history with no baseline (not judged) has no chart, only the table", () => {
    const history = cloneHistory(a15History);
    history.verdict = "not_enough_history";
    history.z = null;
    history.diff = null;
    history.baseline = null;
    const region = detail(history, 5);
    expect(region.querySelector("svg")).toBeNull();
    expect(within(region).queryByRole("img")).not.toBeInTheDocument();
    expect(within(region).getByRole("table", { name: "Weekly totals" })).toBeInTheDocument();
  });

  test("R17 the detail's not_enough_history reason uses the report row's history_weeks", () => {
    // The history window here has 13 weeks (12 baseline + selected), so weeks.length - 1 would say 12:
    // the number must come from the report row (history_weeks 5), not from the length of the window.
    const history = cloneHistory(a15History);
    history.verdict = "not_enough_history";
    history.z = null;
    history.diff = null;
    history.baseline = null;
    history.parameters.min_history_weeks = 8;
    const region = detail(history, 5);
    expect(region.textContent).toContain("5 of 8");
    expect(region.textContent).not.toContain("12 of 8");
  });

  test("R17 end to end: the row's history_weeks reaches the detail through the report", async () => {
    const report = clone(a15Report);
    report.parameters.min_history_weeks = 8;
    const row = report.locations.find((l) => l.location === "Site C") as LocationRow;
    Object.assign(row, { verdict: "not_enough_history", history_weeks: 5, z: null, diff: null, baseline: null });
    const history = cloneHistory(a15History);
    history.verdict = "not_enough_history";
    history.z = null;
    history.diff = null;
    history.baseline = null;
    history.parameters.min_history_weeks = 8;
    installFetch([
      ({ path, account }) =>
        account === "15" && path === "/api/report?week=2026-07-20" ? json(report) : undefined,
      ({ path }) => (path.includes("/history") ? json(history) : undefined),
    ]);
    window.history.pushState(null, "", "/?account=15&week=2026-07-20&location=Site+C");
    render(<App />);
    const region = await screen.findByRole("region", { name: "Location detail" });
    expect(region.textContent).toContain("5 of 8");
  });

  test("R11 a history error is shown with the API's code, not swallowed", async () => {
    installFetch([
      ({ path }) => (path.includes("/history") ? json(errAccountNotFound, 404) : undefined),
    ]);
    window.history.pushState(null, "", "/?account=15&week=2026-07-20&location=Site+C");
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("account_not_found");
  });
});
