import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";

/** Server count of live sessions for the current account (§9: one
 *  adaptive logout button in Profile Security and Settings Security).
 *
 *  Unknown stays null so callers render a loading/retry state — never
 *  an invented single-session label. A stale zero for a live session
 *  re-runs the auth refresh flow and surfaces as retryable, since an
 *  authenticated caller must hold at least one valid session. */
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const r = await api<{ count: number }>("GET", "/api/auth/sessions");
      const n = Number(r.count);
      if (!Number.isFinite(n) || n <= 0) {
        void refresh();
        setCount(null);
        setError(true);
      } else {
        setCount(n);
      }
    } catch {
      setCount(null);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  useEffect(() => {
    void load();
  }, [load]);

  return { count, error, loading, reload: () => void load() };
}
