import { describe, expect, test } from "vitest";

import type { BaselineOut } from "./api/types";
import {
  baselineSentence,
  displayBand,
  fmtAsOf,
  fmtBand,
  fmtDiff,
  fmtNum,
  fmtZ,
  reasonText,
  summaryLabel,
} from "./format";

const MINUS = "−";

function baseline(over: Partial<BaselineOut>): BaselineOut {
  return { median: 0, mad: 0, spread: 0, weeks_used: 12, band_low: 0, band_high: 0, ...over };
}

describe("format (plan §2c F)", () => {
  test("F1 fmtZ rounds to 2 decimals and uses U+2212 for negatives", () => {
    expect(fmtZ(2.7716)).toBe("2.77");
    expect(fmtZ(0.1686)).toBe("0.17");
    expect(fmtZ(-1.2141)).toBe(`${MINUS}1.21`);
    expect(fmtZ(60.4427)).toBe("60.44");
  });

  test("F2 fmtZ never shows a negative zero; null is an em dash", () => {
    expect(fmtZ(-0.004)).toBe("0.00");
    expect(fmtZ(null)).toBe("—");
  });

  test("F3 fmtNum shows at most 1 decimal", () => {
    expect(fmtNum(5.5)).toBe("5.5");
    expect(fmtNum(19)).toBe("19");
    expect(fmtNum(73.5)).toBe("73.5");
    expect(fmtNum(10.1904)).toBe("10.2");
    expect(fmtNum(0.8096)).toBe("0.8");
    expect(fmtNum(880)).toBe("880");
  });

  test("F4 fmtDiff is signed", () => {
    expect(fmtDiff(6.5)).toBe("+6.5");
    expect(fmtDiff(-4.5)).toBe(`${MINUS}4.5`);
    expect(fmtDiff(0)).toBe("0");
  });

  test("F5 displayBand clips the low edge at 0 and fmtBand shows it", () => {
    const shown = displayBand({ band_low: -1.4304, band_high: 10.5 });
    expect(shown).toEqual({ low: 0, high: 10.5 });
    expect(fmtBand({ band_low: -1.4304, band_high: 10.5 })).toBe("0 to 10.5");
  });

  test("F6 fmtBand of a normal band", () => {
    expect(fmtBand({ band_low: 0.8096, band_high: 10.1904 })).toBe("0.8 to 10.2");
  });

  test("F7 fmtAsOf reads the UTC string without a Date", () => {
    expect(fmtAsOf("2026-07-27T22:20:34Z")).toBe("2026-07-27 22:20 UTC");
    expect(fmtAsOf(null)).toBe("—");
  });

  test("F8 the baseline sentence takes its number from the argument", () => {
    expect(baselineSentence(12)).toBe("compared with the last 12 weeks");
    expect(baselineSentence(9)).toBe("compared with the last 9 weeks");
    expect(baselineSentence(1)).toBe("compared with the last 1 week");
  });

  test("F9 the reason for an unjudged row comes from the data and the parameters", () => {
    const params = {
      baseline_weeks: 12,
      min_history_weeks: 8,
      z_min: 2,
      min_abs: 3,
      min_baseline_median: 4,
    };
    const quiet = reasonText(
      { verdict: "too_quiet", history_weeks: 12, baseline: baseline({ median: 3.5 }) },
      params,
    );
    expect(quiet).toContain("3.5");
    expect(quiet).toContain("below 4");

    const young = reasonText({ verdict: "not_enough_history", history_weeks: 5, baseline: null }, params);
    expect(young).toContain("5 of 8 weeks");

    expect(reasonText({ verdict: "no_activity", history_weeks: 0, baseline: null }, params)).toBe(
      "No activity.",
    );
    expect(
      reasonText({ verdict: "higher", history_weeks: 12, baseline: baseline({}) }, params),
    ).toBeNull();
  });
});

describe("summaryLabel (plans/T5-ai-summary.md §2e)", () => {
  test("L1 ai + mock is a preview from the mock provider", () => {
    expect(summaryLabel({ source: "ai", reason: null, provider: "mock" })).toBe(
      "AI summary · preview (mock provider)",
    );
  });

  test("L2 ai + anthropic", () => {
    expect(summaryLabel({ source: "ai", reason: null, provider: "anthropic" })).toBe(
      "AI summary · preview (anthropic)",
    );
  });

  test("L3 a template says why", () => {
    const label = (reason: "disabled" | "nothing_to_summarize" | "provider_error" | "timeout" | "validation_failed") =>
      summaryLabel({ source: "template", reason, provider: "mock" });
    expect(label("disabled")).toBe("Template summary — disabled");
    expect(label("nothing_to_summarize")).toBe("Template summary — nothing to summarize");
    expect(label("provider_error")).toBe("Template summary — provider error");
    expect(label("timeout")).toBe("Template summary — timeout");
    expect(label("validation_failed")).toBe("Template summary — validation failed");
  });

  test("L4 a template never gets the AI wording, whatever the provider", () => {
    for (const provider of ["mock", "anthropic"] as const) {
      const text = summaryLabel({ source: "template", reason: "disabled", provider });
      expect(text).not.toMatch(/AI summary|preview/);
    }
  });
});
