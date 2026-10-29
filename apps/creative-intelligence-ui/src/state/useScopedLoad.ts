import { useEffect, useState } from "react";

interface LoadState<T> {
  load: () => Promise<T>;
  refreshKey: number;
  data: T | null;
  error: string;
  loading: boolean;
}

/** Memoize load with every input that determines its response. */
export function useScopedLoad<T>(load: () => Promise<T>, refreshKey = 0) {
  const [state, setState] = useState<LoadState<T>>(() => ({
    load, refreshKey, data: null, error: "", loading: true,
  }));

  useEffect(() => {
    let live = true;
    setState({ load, refreshKey, data: null, error: "", loading: true });
    void (async () => {
      try {
        const data = await load();
        if (live) setState({ load, refreshKey, data, error: "", loading: false });
      } catch (error) {
        if (!live) return;
        const message = error instanceof Error ? error.message : String(error);
        setState({ load, refreshKey, data: null, error: message || "Request Failed", loading: false });
      }
    })();
    return () => { live = false; };
  }, [load, refreshKey]);

  // A new scope must hide old values on its first render, before effects run.
  if (state.load !== load || !Object.is(state.refreshKey, refreshKey)) {
    return { data: null, error: "", loading: true };
  }
  return { data: state.data, error: state.error, loading: state.loading };
}
