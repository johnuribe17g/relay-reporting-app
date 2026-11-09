// Pure layout for the weekly chart (plans/T4-frontend.md §2c C). All the arithmetic is here; WeekChart only
// draws this output. Layout math only: no statistic is computed. The band is clipped through displayBand,
// the one clipping function, never here.
import type { BaselineOut, WeekPoint } from "./api/types";
import { displayBand } from "./format";

export interface Padding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface ChartInput {
  points: Pick<WeekPoint, "total">[];
  band: Pick<BaselineOut, "band_low" | "band_high"> | null;
  width: number;
  height: number;
  padding: Padding;
}

export interface ChartGeometry {
  /** x of each point: evenly spread over the plot, a single point centered. */
  xs: number[];
  /** y of each point; the Y axis starts at 0. */
  ys: number[];
  /** Top of the Y axis: covers the data and the band's top edge, and is at least 1. */
  yMax: number;
  plot: { left: number; right: number; top: number; bottom: number };
  /** The shaded band over the full plot width, or null (no band, or no points). */
  bandRect: { x: number; width: number; y: number; height: number } | null;
}

export function chartGeometry({ points, band, width, height, padding }: ChartInput): ChartGeometry {
  const left = padding.left;
  const right = width - padding.right;
  const top = padding.top;
  const bottom = height - padding.bottom;
  const innerWidth = right - left;
  const innerHeight = bottom - top;
  const plot = { left, right, top, bottom };

  const shown = band === null ? null : displayBand(band);
  const dataMax = points.reduce((max, point) => Math.max(max, point.total), 0);
  const yMax = Math.max(dataMax, shown?.high ?? 0, 1);
  const yOf = (value: number): number => top + innerHeight * (1 - value / yMax);

  if (points.length === 0) return { xs: [], ys: [], yMax, plot, bandRect: null };

  const xs = points.map((_, i) =>
    points.length === 1 ? left + innerWidth / 2 : left + (i * innerWidth) / (points.length - 1),
  );
  const ys = points.map((point) => yOf(point.total));
  const bandRect =
    shown === null
      ? null
      : { x: left, width: innerWidth, y: yOf(shown.high), height: yOf(shown.low) - yOf(shown.high) };
  return { xs, ys, yMax, plot, bandRect };
}
