import { useEffect, useMemo, useState } from "react";

import { getAccounts, getHistory, getReport, getWeeks } from "./api/client";
import type { History, Report } from "./api/types";
import { AccountSwitcher } from "./components/AccountSwitcher";
import { ErrorBox } from "./components/ErrorBox";
import { LocationDetail } from "./components/LocationDetail";
import { AccountSummary } from "./components/AccountSummary";
import { LocationTable } from "./components/LocationTable";
import { Notice } from "./components/Notice";
import { WeekSelector } from "./components/WeekSelector";
import { useAsync, type AsyncState } from "./hooks/useAsync";
import { useUrlState } from "./hooks/useUrlState";
import { reconcileAccount, reconcileLocation, reconcileWeek } from "./reconcile";
import { buildUrl, nextOnAccount, nextOnLocation, nextOnWeek } from "./urlState";

interface WeekNotice {
  account: string;
  week: string | null;
  text: string;
}

/**
 * Request waterfall (D-27). With an account in the URL: /api/accounts, then /api/weeks only if the
 * account is listed, then /api/report, then /api/locations/../history. With no account in the URL:
 * /api/accounts and the header-less /api/weeks run in parallel, and the account the server answered
 * for is adopted into the URL (replaceState).
 */
export default function App() {
  const { url, push, replace } = useUrlState();

  // `scope` is the account the weeks request is for (null = header-less bootstrap). It follows the URL,
  // except right after adoption, when the URL gains the account the server chose: that is not a change.
  const [scope, setScope] = useState<string | null>(url.account);
  const [adopted, setAdopted] = useState<string | undefined>(undefined);
  if (url.account !== scope && url.account !== adopted) {
    setScope(url.account);
    setAdopted(undefined);
  }
  const [notice, setNotice] = useState<WeekNotice | null>(null);

  const accounts = useAsync("accounts", (signal) => getAccounts(signal));
  const accountCheck =
    scope !== null && accounts.status === "ok" ? reconcileAccount(scope, accounts.data) : null;

  const weeksKey =
    scope === null ? "weeks:default" : accountCheck?.kind === "ok" ? `weeks:${scope}` : null;
  const weeks = useAsync(weeksKey, (signal) => getWeeks(scope, signal));
  const weeksData = weeks.status === "ok" ? weeks.data : null;
  const accountId = weeksData === null ? null : String(weeksData.account.id);
  const weekResult = useMemo(
    () => (weeksData === null ? null : reconcileWeek(url.week, weeksData)),
    [weeksData, url.week],
  );

  // Adopt the account, correct the week (one replaceState), remember the notice for a stale week.
  // It cannot loop: `replace` runs only when the URL differs from `desired`, after which they are equal,
  // and `setNotice`/`setAdopted` keep the previous value when nothing changed (no re-render).
  useEffect(() => {
    if (weekResult === null || accountId === null) return;
    if (scope === null) setAdopted(accountId);
    const text = weekResult.notice;
    if (text !== null) {
      setNotice((prev) =>
        prev?.account === accountId && prev.week === weekResult.week && prev.text === text
          ? prev
          : { account: accountId, week: weekResult.week, text },
      );
    }
    const current = { account: url.account, week: url.week, location: url.location };
    const desired = { account: accountId, week: weekResult.week, location: url.location };
    if (buildUrl(desired) !== buildUrl(current)) replace(desired);
  }, [weekResult, accountId, scope, url.account, url.week, url.location, replace]);

  const reportKey =
    accountId !== null && weekResult !== null ? `report:${accountId}:${weekResult.week ?? "none"}` : null;
  const report = useAsync<Report>(reportKey, (signal) =>
    getReport(accountId as string, weekResult?.week ?? null, signal),
  );
  const reportData = report.status === "ok" ? report.data : null;
  const locationResult = useMemo(
    () => (reportData === null ? null : reconcileLocation(url.location, reportData)),
    [reportData, url.location],
  );

  // Drop a location the report does not have. Once dropped, `corrected` is false again: no loop.
  const locationCorrected = locationResult?.corrected ?? false;
  useEffect(() => {
    if (locationCorrected) replace({ account: url.account, week: url.week, location: null });
  }, [locationCorrected, url.account, url.week, replace]);

  const selected = locationResult?.location ?? null;
  const historyKey =
    reportData !== null && reportData.week !== null && selected !== null
      ? `history:${accountId}:${reportData.week}:${selected}`
      : null;
  const history = useAsync(historyKey, (signal) =>
    getHistory(accountId as string, selected as string, reportData?.week as string, signal),
  );

  const listed = accounts.status === "ok" ? accounts.data : null;
  const current = accountId ?? url.account ?? "";
  const switcherValue = listed?.some((a) => String(a.id) === current) ? current : "";
  const shownNotice =
    notice !== null && notice.account === accountId && notice.week === weekResult?.week
      ? notice.text
      : null;

  return (
    <div>
      <header>
        <h1>Relay report</h1>
        <AccountSwitcher
          accounts={listed}
          value={switcherValue}
          onChange={(id) => push(nextOnAccount(url, id))}
        />{" "}
        <WeekSelector
          weeks={weeksData?.weeks ?? []}
          value={weekResult?.week ?? null}
          onChange={(week) => push(nextOnWeek(url, week))}
        />
      </header>
      {shownNotice !== null && <Notice text={shownNotice} />}
      <main>
        {accounts.status === "error" ? (
          <ErrorBox code={accounts.error.code} message={accounts.error.message} />
        ) : scope !== null && accounts.status !== "ok" ? (
          <p>Loading…</p>
        ) : accountCheck?.kind === "error" ? (
          <ErrorBox code={accountCheck.code} message={accountCheck.message} />
        ) : weeks.status === "error" ? (
          <ErrorBox code={weeks.error.code} message={weeks.error.message} />
        ) : report.status === "error" ? (
          <ErrorBox code={report.error.code} message={report.error.message} />
        ) : reportData === null ? (
          <p>Loading…</p>
        ) : (
          <ReportView
            report={reportData}
            selected={selected}
            history={history}
            onSelect={(location) => push(nextOnLocation(url, location))}
          />
        )}
      </main>
    </div>
  );
}

function ReportView({
  report,
  selected,
  history,
  onSelect,
}: {
  report: Report;
  selected: string | null;
  history: AsyncState<History>;
  onSelect: (location: string) => void;
}) {
  if (report.week === null) {
    const verdict = report.account_summary.verdict;
    return (
      <p>
        {verdict === "no_activity"
          ? "This account has no activity yet."
          : verdict === "not_enough_history"
            ? "Not enough history yet to judge any week."
            : "There is no week to show."}
      </p>
    );
  }
  return (
    <>
      <AccountSummary report={report} />
      <section>
        <h3>Locations</h3>
        <LocationTable
          locations={report.locations}
          parameters={report.parameters}
          selected={selected}
          onSelect={onSelect}
        />
      </section>
      <section>
        <LocationDetail location={selected} history={history} />
      </section>
    </>
  );
}
