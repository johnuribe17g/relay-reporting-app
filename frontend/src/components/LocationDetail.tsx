import type { History } from "../api/types";
import type { AsyncState } from "../hooks/useAsync";
import { ErrorBox } from "./ErrorBox";

/** CP1b minimal: fetches the history and shows the heading. CP3a replaces it with the real detail. */
export function LocationDetail({
  location,
  history,
}: {
  location: string | null;
  history: AsyncState<History>;
}) {
  if (location === null) return <p>Select a location to see its history.</p>;
  if (history.status === "error") {
    return <ErrorBox code={history.error.code} message={history.error.message} />;
  }
  if (history.status !== "ok") return <p>Loading…</p>;
  return <h2>{history.data.location}</h2>;
}
