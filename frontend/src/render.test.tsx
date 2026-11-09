import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import App from "./App";
import type { LocationRow, Report, Verdict } from "./api/types";
import { AccountSummary } from "./components/AccountSummary";
import { LocationTable } from "./components/LocationTable";
import a15Report from "./test/fixtures/a15-report-0720.json";
import a20Report from "./test/fixtures/a20-report.json";
import a6Report0601 from "./test/fixtures/a6-report-0601.json";
import a6Report0720 from "./test/fixtures/a6-report-0720.json";
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
