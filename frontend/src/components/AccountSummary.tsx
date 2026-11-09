import type { Report } from "../api/types";
import {
  baselineSentence,
  fmtAsOf,
  fmtBand,
  fmtDiff,
  fmtNum,
  fmtZ,
  reasonText,
  verdictLabel,
} from "../format";
import { DataQualityWarning } from "./DataQualityWarning";

/** The account verdict for the selected week, the total against its normal, and the per-type breakdown. */
export function AccountSummary({ report }: { report: Report }) {
  const summary = report.account_summary;
  const baseline = summary.baseline;
  const reason = reasonText(summary, report.parameters);
  return (
    <section aria-label="Account summary" data-verdict={summary.verdict}>
      <h2>Week of {report.week}</h2>
      <p>
        Account: <strong>{verdictLabel(summary.verdict)}</strong>
      </p>
      {reason !== null && <p>{reason}</p>}
      <dl>
        <div>
          <dt>Events this week</dt>
          <dd>{fmtNum(summary.total)}</dd>
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
          <dd>{fmtZ(summary.z)}</dd>
        </div>
        <div>
          <dt>Difference</dt>
          <dd>{fmtDiff(summary.diff)}</dd>
        </div>
        {summary.by_type !== null && (
          <>
            <div>
              <dt>Calls</dt>
              <dd>{summary.by_type.call_received}</dd>
            </div>
            <div>
              <dt>Leads</dt>
              <dd>{summary.by_type.lead_created}</dd>
            </div>
            <div>
              <dt>Appointments</dt>
              <dd>{summary.by_type.appointment_set}</dd>
            </div>
          </>
        )}
      </dl>
      {baseline !== null && <p>This week&apos;s total, {baselineSentence(baseline.weeks_used)}.</p>}
      <p>
        Account time zone: {report.account.timezone}. Data through {fmtAsOf(report.as_of)}.
      </p>
      {summary.data_quality.unknown_events_in_window > 0 && (
        <DataQualityWarning count={summary.data_quality.unknown_events_in_window} />
      )}
    </section>
  );
}
