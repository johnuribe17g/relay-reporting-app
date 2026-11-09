import type { History } from "../api/types";
import { baselineSentence, fmtBand, fmtDiff, fmtNum, fmtZ, reasonText, verdictLabel } from "../format";
import type { AsyncState } from "../hooks/useAsync";
import { DataQualityWarning } from "./DataQualityWarning";
import { ErrorBox } from "./ErrorBox";
import { WeekChart } from "./WeekChart";
import { WeeksTable } from "./WeeksTable";

/**
 * One location: its verdict and numbers for the selected week, and the weeks (about 12 baseline weeks plus the
 * selected one) against the one band the API returned. Everything is rendered as given.
 */
export function LocationDetail({
  location,
  historyWeeks,
  history,
}: {
  location: string | null;
  /** The location's `history_weeks` from the report row (the history response does not carry it). */
  historyWeeks: number | null;
  history: AsyncState<History>;
}) {
  if (location === null) return <p>Select a location to see its history.</p>;
  if (history.status === "error") {
    return <ErrorBox code={history.error.code} message={history.error.message} />;
  }
  if (history.status !== "ok") return <p>Loading…</p>;

  const data = history.data;
  const baseline = data.baseline;
  const selected = data.weeks.find((point) => point.role === "selected");
  const reason =
    historyWeeks === null
      ? null
      : reasonText({ verdict: data.verdict, history_weeks: historyWeeks, baseline }, data.parameters);
  return (
    <section aria-label="Location detail" data-verdict={data.verdict}>
      <h2>{data.location}</h2>
      <p>
        Selected week {data.week}: <strong>{verdictLabel(data.verdict)}</strong>
      </p>
      {reason !== null && <p>{reason}</p>}
      <dl>
        <div>
          <dt>This week</dt>
          <dd>{fmtNum(selected?.total ?? null)}</dd>
        </div>
        <div>
          <dt>Normal (median)</dt>
          <dd>{baseline === null ? "—" : fmtNum(baseline.median)}</dd>
        </div>
        <div>
          <dt>Normal range</dt>
          <dd>{baseline === null ? "—" : `${fmtBand(baseline)} (the edges count as unusual)`}</dd>
        </div>
        <div>
          <dt>Score (z)</dt>
          <dd>{fmtZ(data.z)}</dd>
        </div>
        <div>
          <dt>Difference</dt>
          <dd>{fmtDiff(data.diff)}</dd>
        </div>
      </dl>
      {baseline !== null && <p>This week&apos;s total, {baselineSentence(baseline.weeks_used)}.</p>}
      {data.data_quality.unknown_events_in_window > 0 && (
        <DataQualityWarning count={data.data_quality.unknown_events_in_window} />
      )}
      <WeekChart data={data} />
      <WeeksTable weeks={data.weeks} />
    </section>
  );
}
