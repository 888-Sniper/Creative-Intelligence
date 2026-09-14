import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";

/** How long a session-count check may run before it counts as failed. */
export const SESSION_CHECK_TIMEOUT_MS = 10000;

/** Server count of live sessions for the current account (§9: one
 *  adaptive logout button in Profile Security and Settings Security).
 *
 *  Unknown stays null so callers render a loading/retry state — never
 *  an invented single-session label. A stale zero for a live session
 *  re-runs the auth refresh flow and surfaces as retryable, since an
 *  authenticated caller must hold at least one valid session.
 *
 *  Loading is bounded (§11): a hung request fails after
 *  SESSION_CHECK_TIMEOUT_MS instead of sticking on "Checking…"
 *  forever. Overlapping reloads share one in-flight request, and
 *  unmounted or superseded responses are dropped.
 */
export function useSessionCount(): {
  count: number | null;
  error: boolean;
  loading: boolean;
  reload: () => void;
} {
  const { refresh } = useAuth();
  const [count, setCount] = useState<number | null>(null);
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
      const timeout = new Promise<never>((_, reject) => {
        window.setTimeout(() => reject(new Error("Session check timed out.")), SESSION_CHECK_TIMEOUT_MS);
      });
      try {
        const r = await Promise.race([
          api<{ count: number }>("GET", "/api/auth/sessions"),
          timeout,
        ]);
        if (!live.current || my !== seq.current) return;
        const n = Number(r.count);
        if (!Number.isFinite(n) || n <= 0) {
          void refresh();
          setCount(null);
          setError(true);
        } else {
          setCount(n);
        }
      } catch {
        if (!live.current || my !== seq.current) return;
        setCount(null);
        setError(true);
      } finally {
        if (live.current && my === seq.current) setLoading(false);
        if (inflight.current === run) inflight.current = null;
      }
    })();
    inflight.current = run;
    return run;
  }, [refresh]);

  useEffect(() => {
    void load();
  }, [load]);

  return { count, error, loading, reload: () => void load() };
}
