import { useCallback, useEffect, useState } from "react";

import { buildUrl, parseUrl, type UrlState } from "../urlState";

/** URL state over URLSearchParams and history. User changes push; corrections replace; popstate re-reads. */
export function useUrlState(): {
  url: UrlState;
  push: (next: UrlState) => void;
  replace: (next: UrlState) => void;
} {
  const [url, setUrl] = useState<UrlState>(() => parseUrl(window.location.search));

  useEffect(() => {
    const onPop = (): void => setUrl(parseUrl(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const write = useCallback((mode: "push" | "replace", next: UrlState): void => {
    const search = buildUrl(next);
    if (search !== window.location.search) {
      const target = window.location.pathname + search;
      if (mode === "push") window.history.pushState(null, "", target);
      else window.history.replaceState(null, "", target);
    }
    setUrl(parseUrl(search));
  }, []);

  const push = useCallback((next: UrlState) => write("push", next), [write]);
  const replace = useCallback((next: UrlState) => write("replace", next), [write]);
  return { url, push, replace };
}
