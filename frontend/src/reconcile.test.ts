import { describe, expect, test } from "vitest";

import { reconcileAccount, reconcileLocation, reconcileWeek } from "./reconcile";

const accounts = [
  { id: 1, name: "A", timezone: "America/Chicago" },
  { id: 2, name: "B", timezone: "America/Denver" },
  { id: 15, name: "C", timezone: "America/Phoenix" },
];
const weeksOut = {
  weeks: ["2026-03-30", "2026-04-06", "2026-04-13"],
  default_week: "2026-04-13" as string | null,
};
const noWeeks = { weeks: [] as string[], default_week: null };

describe("reconcileAccount (plan §2b RA)", () => {
  test("RA1 no account param is the header-less bootstrap", () => {
    expect(reconcileAccount(null, accounts)).toEqual({ kind: "default" });
  });

  test("RA2 a listed account is ok", () => {
    expect(reconcileAccount("15", accounts)).toEqual({ kind: "ok", id: "15" });
  });

  test.each(["999", "abc", "0", "-1", "015"])("RA3 %s is not a listed account", (param) => {
    // none equals String(id) of 1, 2 or 15
    const result = reconcileAccount(param, accounts);
    expect(result.kind).toBe("error");
    if (result.kind === "error") {
      expect(result.code).toBe("unknown_account");
      expect(result.message).toContain(param);
    }
  });

  test("RA4 an empty account list (DB not seeded) rejects every id", () => {
    expect(reconcileAccount("15", []).kind).toBe("error");
  });
});

describe("reconcileWeek (plan §2b RW)", () => {
  test("RW1 a listed week is kept", () => {
    expect(reconcileWeek("2026-04-06", weeksOut)).toEqual({
      week: "2026-04-06",
      corrected: false,
      notice: null,
    });
  });

  test("RW2 no week param adopts the default without a notice", () => {
    expect(reconcileWeek(null, weeksOut)).toEqual({
      week: "2026-04-13",
      corrected: true,
      notice: null,
    });
  });

  test("RW3 a Monday before the range falls back with a notice naming both weeks", () => {
    const r = reconcileWeek("2026-01-05", weeksOut);
    expect(r.week).toBe("2026-04-13");
    expect(r.corrected).toBe(true);
    expect(r.notice).toContain("2026-01-05");
    expect(r.notice).toContain("2026-04-13");
  });

  test.each(["abc", "2026-04-07"])("RW4 %s (malformed, or a Tuesday) behaves like RW3", (param) => {
    const r = reconcileWeek(param, weeksOut);
    expect(r.week).toBe("2026-04-13");
    expect(r.corrected).toBe(true);
    expect(r.notice).toContain(param);
    expect(r.notice).toContain("2026-04-13");
  });

  test("RW5 no selectable weeks and no param: null, nothing to correct", () => {
    expect(reconcileWeek(null, noWeeks)).toEqual({ week: null, corrected: false, notice: null });
  });

  test("RW6 no selectable weeks and a stale param: removed, no notice", () => {
    expect(reconcileWeek("2026-04-06", noWeeks)).toEqual({
      week: null,
      corrected: true,
      notice: null,
    });
  });
});

describe("reconcileLocation (plan §2b RL)", () => {
  const report = { locations: [{ location: "Site A" }, { location: "Site C" }] };

  test("RL1 no location param", () => {
    expect(reconcileLocation(null, report)).toEqual({ location: null, corrected: false });
  });

  test("RL2 a location in the report is kept", () => {
    expect(reconcileLocation("Site C", report)).toEqual({ location: "Site C", corrected: false });
  });

  test("RL3 the match is exact, no case folding (D-06)", () => {
    expect(reconcileLocation("site c", report)).toEqual({ location: null, corrected: true });
  });

  test("RL4 an unknown location, or any location with no rows, is dropped", () => {
    expect(reconcileLocation("Nope", report)).toEqual({ location: null, corrected: true });
    expect(reconcileLocation("Site C", { locations: [] })).toEqual({
      location: null,
      corrected: true,
    });
  });
});
