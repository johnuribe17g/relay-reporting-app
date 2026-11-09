import { useEffect, useRef, useState } from "react";

import { postSummary, type ApiError } from "../api/client";
import type { SummaryOut } from "../api/types";
import { summaryLabel } from "../format";
import { toApiError } from "../hooks/useAsync";
import { ErrorBox } from "./ErrorBox";

/** Decorative: hidden from assistive technology, so the button's accessible name is unchanged. */
function Sparkle() {
  return (
    <span aria-hidden="true" data-part="sparkle">
      ✦
    </span>
  );
}

type Result =
  | { status: "loading" }
  | { status: "ok"; data: SummaryOut }
  | { status: "error"; error: ApiError };

/**
 * The AI summary card (plans/T5-ai-summary.md §1f). Always rendered, whatever the server's flag.
 * Nothing is requested until the button is clicked: that click is the opt-in. The result belongs to
 * the (account, week) it was requested for and is dropped when either changes; a late response for a
 * previous key is ignored. All text is rendered as text, never as HTML.
 */
export function SummaryCard({ account, week }: { account: string; week: string | null }) {
  const key = `${account}:${week ?? "none"}`;
  const [stored, setStored] = useState<{ key: string; result: Result } | null>(null);
  const controller = useRef<AbortController | null>(null);

  // A new key (or unmount) aborts a request still in flight.
  useEffect(() => () => controller.current?.abort(), [key]);

  function generate(): void {
    controller.current?.abort();
    const own = new AbortController();
    controller.current = own;
    setStored({ key, result: { status: "loading" } });
    postSummary(account, week, own.signal).then(
      (data) => {
        if (!own.signal.aborted) setStored({ key, result: { status: "ok", data } });
      },
      (error: unknown) => {
        if (own.signal.aborted) return;
        setStored({ key, result: { status: "error", error: toApiError(error) } });
      },
    );
  }

  const result = stored !== null && stored.key === key ? stored.result : null;
  return (
    <section aria-label="AI summary">
      <h3>Summary</h3>
      {result === null && <p>Uses AI when enabled; otherwise a template built from the same data.</p>}
      <button type="button" onClick={generate} disabled={result?.status === "loading"}>
        <Sparkle /> Generate summary
      </button>
      {result?.status === "loading" && <p>Generating summary…</p>}
      {result?.status === "error" && (
        <ErrorBox code={result.error.code} message={result.error.message} />
      )}
      {result?.status === "ok" && (
        <div>
          <p>
            <em>
              {result.data.source === "ai" && (
                <>
                  <Sparkle />{" "}
                </>
              )}
              <span>{summaryLabel(result.data)}</span>
            </em>
          </p>
          {result.data.headline !== null && (
            <p data-part="headline">
              <strong>{result.data.headline}</strong>
            </p>
          )}
          {result.data.text.split("\n").map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
      )}
    </section>
  );
}
