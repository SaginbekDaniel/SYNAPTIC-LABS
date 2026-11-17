import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

export interface ApiOptions {
  /**
   * Keep the previous key's data on screen while the next key loads, as long as `scope`
   * is unchanged (e.g. paging or re-filtering the same dataset). A new scope always clears.
   */
  scope?: string;
}

/**
 * Fetch on mount and whenever `key` changes. Data from a previous key is cleared
 * immediately so a stale dataset/alert is never shown under a new selection,
 * unless `options.scope` says the new key is a refinement of the same view.
 */
export function useApi<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>, options?: ApiOptions): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(key !== null);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const lastKey = useRef<string | null>(null);
  const lastScope = useRef<string | undefined>(undefined);
  const scope = options?.scope;

  useEffect(() => {
    if (key === null) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    if (lastKey.current !== key) {
      if (scope === undefined || scope !== lastScope.current) setData(null);
      lastKey.current = key;
      lastScope.current = scope;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    fetcherRef
      .current(ctrl.signal)
      .then((d) => {
        if (!ctrl.signal.aborted) setData(d);
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted || (e as Error).name === "AbortError") return;
        setError(e instanceof ApiError ? e : new ApiError(0, "UNEXPECTED", String(e), null));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
    // `scope` is read only when `key` changes; callers include the scope in the key.
  }, [key, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}
