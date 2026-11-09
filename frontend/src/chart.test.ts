import { describe, expect, test } from "vitest";

import { chartGeometry } from "./chart";

// Width 300, height 100, padding 10 on every side: the plot is 280 x 80 (plan §2c).
const layout = { width: 300, height: 100, padding: { top: 10, right: 10, bottom: 10, left: 10 } };
const totals = (values: number[]): { total: number }[] => values.map((total) => ({ total }));

function expectClose(actual: number[], expected: number[]): void {
  expect(actual).toHaveLength(expected.length);
  expected.forEach((value, i) => expect(actual[i]).toBeCloseTo(value, 3));
}

describe("chartGeometry (plan §2c C)", () => {
  test("C1 totals [2,4,6], band -1..5: yMax 6, the band's low edge is clipped at 0", () => {
    // yMax = max(6, 5) = 6; x = 10 + i*280/2 = 10, 150, 290; y = 10 + 80*(1 - v/6): 2 -> 63.333, 4 -> 36.667, 6 -> 10
    // band: low -1 shown as 0 -> y 90; high 5 -> y = 10 + 80/6 = 23.333; height = 90 - 23.333 = 66.667
    const g = chartGeometry({ ...layout, points: totals([2, 4, 6]), band: { band_low: -1, band_high: 5 } });
    expect(g.yMax).toBe(6);
    expectClose(g.xs, [10, 150, 290]);
    expectClose(g.ys, [63.333, 36.667, 10]);
    expect(g.bandRect?.y).toBeCloseTo(23.333, 3);
    expect(g.bandRect?.height).toBeCloseTo(66.667, 3);
  });

  test("C2 the same totals, band 1..5: a positive low edge is kept", () => {
    // low 1 -> y = 10 + 80*(5/6) = 76.667; high 5 -> 23.333; height 53.333
    const g = chartGeometry({ ...layout, points: totals([2, 4, 6]), band: { band_low: 1, band_high: 5 } });
    expect(g.bandRect?.y).toBeCloseTo(23.333, 3);
    expect(g.bandRect?.height).toBeCloseTo(53.333, 3);
  });

  test("C3 totals [1,2], band 2..8: yMax covers the band's top edge", () => {
    // yMax = 8; y(1) = 10 + 80*7/8 = 80; y(2) = 10 + 80*6/8 = 70; band y(8) = 10 to y(2) = 70, height 60
    const g = chartGeometry({ ...layout, points: totals([1, 2]), band: { band_low: 2, band_high: 8 } });
    expect(g.yMax).toBe(8);
    expectClose(g.ys, [80, 70]);
    expect(g.bandRect?.y).toBeCloseTo(10, 3);
    expect(g.bandRect?.height).toBeCloseTo(60, 3);
  });

  test("C4 one point, total 3, no band: centered, no rect", () => {
    // n = 1 -> x = 10 + 280/2 = 150; yMax 3 -> y = 10
    const g = chartGeometry({ ...layout, points: totals([3]), band: null });
    expectClose(g.xs, [150]);
    expectClose(g.ys, [10]);
    expect(g.bandRect).toBeNull();
  });

  test("C5 totals [0,0], no band: yMax is at least 1, no division by zero", () => {
    // yMax = max(0, 1) = 1; y = 10 + 80*(1 - 0) = 90
    const g = chartGeometry({ ...layout, points: totals([0, 0]), band: null });
    expect(g.yMax).toBe(1);
    expectClose(g.ys, [90, 90]);
  });

  test("C6 no points: empty arrays and no rect, even with a band", () => {
    const g = chartGeometry({ ...layout, points: [], band: { band_low: 1, band_high: 5 } });
    expect(g.xs).toEqual([]);
    expect(g.ys).toEqual([]);
    expect(g.bandRect).toBeNull();
  });
});
