import { chartGeometry } from "../chart";
import type { History } from "../api/types";
import { fmtBand, fmtNum } from "../format";

// One series, so one color and no legend box (the heading names it). Colors are presentation attributes, so
// a stylesheet can override them through the data-role / data-chart hooks.
const WIDTH = 640;
const HEIGHT = 240;
const PADDING = { top: 24, right: 32, bottom: 32, left: 44 };
const SERIES = "#2a78d6";
const SURFACE = "#fcfcfb";
const AXIS = "#d5d4cf";
const TEXT = "#52514e";
const TEXT_STRONG = "#0b0b0b";

/**
 * The weekly totals as a line with a point per week, the selected week's point larger and labeled, over
 * the selected week's normal range as a shaded band. Earlier points outside the band are not styled as
 * alerts: the band is only the selected week's range. No chart when the history has no baseline.
 */
export function WeekChart({ data }: { data: History }) {
  const baseline = data.baseline;
  if (baseline === null) return null;

  const g = chartGeometry({
    points: data.weeks,
    band: baseline,
    width: WIDTH,
    height: HEIGHT,
    padding: PADDING,
  });
  const first = data.weeks[0];
  const last = data.weeks[data.weeks.length - 1];
  const selected = data.weeks.find((point) => point.role === "selected");
  const band = fmtBand(baseline);
  const label =
    `${data.location}: weekly totals over ${data.weeks.length} weeks; ` +
    `selected week ${data.week} total ${fmtNum(selected?.total ?? null)}; normal range ${band}.`;
  const line = g.xs.map((x, i) => `${x.toFixed(1)},${(g.ys[i] ?? 0).toFixed(1)}`).join(" ");

  return (
    <figure>
      <svg role="img" aria-label={label} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%">
        {g.bandRect !== null && (
          <rect
            data-chart="band"
            x={g.bandRect.x}
            y={g.bandRect.y}
            width={g.bandRect.width}
            height={g.bandRect.height}
            fill={SERIES}
            fillOpacity={0.12}
          />
        )}
        <line x1={g.plot.left} y1={g.plot.bottom} x2={g.plot.right} y2={g.plot.bottom} stroke={AXIS} strokeWidth={1} />
        <line x1={g.plot.left} y1={g.plot.top} x2={g.plot.left} y2={g.plot.bottom} stroke={AXIS} strokeWidth={1} />
        <text x={g.plot.left - 8} y={g.plot.bottom + 4} textAnchor="end" fontSize={12} fill={TEXT}>
          0
        </text>
        <text x={g.plot.left - 8} y={g.plot.top + 4} textAnchor="end" fontSize={12} fill={TEXT}>
          {fmtNum(g.yMax)}
        </text>
        {first !== undefined && (
          <text x={g.plot.left} y={g.plot.bottom + 20} textAnchor="start" fontSize={12} fill={TEXT}>
            {first.week}
          </text>
        )}
        {last !== undefined && (
          <text x={g.plot.right} y={g.plot.bottom + 20} textAnchor="end" fontSize={12} fill={TEXT}>
            {last.week}
          </text>
        )}
        <polyline
          points={line}
          fill="none"
          stroke={SERIES}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {data.weeks.map((point, i) => (
          <circle
            key={point.week}
            data-role={point.role}
            cx={g.xs[i]}
            cy={g.ys[i]}
            r={point.role === "selected" ? 6 : 4}
            fill={SERIES}
            stroke={SURFACE}
            strokeWidth={2}
          >
            <title>{`${point.week}: ${point.total} events${point.role === "selected" ? " (selected week)" : ""}`}</title>
          </circle>
        ))}
        {data.weeks.map((point, i) =>
          point.role === "selected" ? (
            <text
              key={`label-${point.week}`}
              x={g.xs[i]}
              y={(g.ys[i] ?? 0) - 12}
              textAnchor="middle"
              fontSize={12}
              fontWeight={600}
              fill={TEXT_STRONG}
            >
              {point.total}
            </text>
          ) : null,
        )}
      </svg>
      <figcaption>
        Shaded: normal range for the selected week ({band}). Earlier weeks are shown for context and are
        not judged against it.
      </figcaption>
    </figure>
  );
}
