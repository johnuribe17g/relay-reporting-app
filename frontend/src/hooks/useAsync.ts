import { useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";

export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "error"; error: ApiError };

type Result<T> = { status: "ok"; data: T } | { status: "error"; error: ApiError };

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "unexpected_error", error instanceof Error ? error.message : "Unexpected error.");
}

/**
 * The one place that fetches. `key` identifies the request (null = nothing to do). A new key aborts the
 * previous request and its result is ignored, so a late response can never overwrite the current one;
 * an aborted request never produces an error state. The result is tagged with its key, so a render under
 * a new key shows `loading`, never the previous key's data.
 */
export function useAsync<T>(
  key: string | null,
  fn: (signal: AbortSignal) => Promise<T>,
): AsyncState<T> {
  const [stored, setStored] = useState<{ key: string; result: Result<T> } | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    let live = true;
    fnRef.current(controller.signal).then(
      (data) => {
        if (live) setStored({ key, result: { status: "ok", data } });
      },
      (error: unknown) => {
        // Aborted by us (superseded or unmounted): silent, never an ErrorBox.
        if (!live || controller.signal.aborted) return;
        setStored({ key, result: { status: "error", error: toApiError(error) } });
      },
    );
    return () => {
      live = false;
      controller.abort();
    };
  }, [key]);

  if (key === null) return { status: "idle" };
  if (stored === null || stored.key !== key) return { status: "loading" };
  return stored.result;
}
