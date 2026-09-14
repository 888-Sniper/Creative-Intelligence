import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";

/** How long a Google integration-status check may run before it
 *  counts as failed. */
export const GOOGLE_STATUS_TIMEOUT_MS = 10000;

/** Bounded Google Drive connection check (§11): the same loading
 *  bound, retry handling and in-flight guard as the session-count
 *  hook. A stalled request fails after GOOGLE_STATUS_TIMEOUT_MS
 *  instead of sticking on "Checking…" forever; overlapping reloads
 *  share one in-flight request, and unmounted or superseded
 *  responses are dropped.
 *
 *  Unknown stays null so callers render a loading/retry state —
 *  never an invented connected/disconnected label.
 */
export function useGoogleStatus(): {
  connected: boolean | null;
  error: boolean;
  loading: boolean;
  reload: () => void;
} {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const live = useRef(true);
  const inflight = useRef<Promise<void> | null>(null);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  const load = useCallback(() => {
    if (inflight.current) return inflight.current;
    const my = ++seq.current;
    setLoading(true);
    setError(false);
    let run!: Promise<void>;
    run = (async () => {
      try {
        const r = await api<{ connected: boolean }>(
          "GET",
          "/api/auth/google/status",
          undefined,
          { timeoutMs: GOOGLE_STATUS_TIMEOUT_MS },
        );
        if (!live.current || my !== seq.current) return;
        setConnected(r.connected === true);
      } catch {
        if (!live.current || my !== seq.current) return;
        setConnected(null);
        setError(true);
      } finally {
        if (live.current && my === seq.current) setLoading(false);
        if (inflight.current === run) inflight.current = null;
      }
    })();
    inflight.current = run;
    return run;
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { connected, error, loading, reload: () => void load() };
}
