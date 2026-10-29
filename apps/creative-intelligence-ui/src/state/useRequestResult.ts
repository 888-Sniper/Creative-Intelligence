import { useLayoutEffect, useRef, useState } from "react";

interface RequestState<T> {
  key: string;
  data: T | null;
  loading: boolean;
  error: string;
}

function empty<T>(key: string): RequestState<T> {
  return { key, data: null, loading: false, error: "" };
}

/** Manual requests belong to one committed input key and one invocation.
 * Obsolete work may finish, but cannot publish data, errors or loading state.
 */
export function useRequestResult<T>(key: string, fallbackError = "Request Failed") {
  const [state, setState] = useState<RequestState<T>>(() => empty<T>(key));
  const owner = useRef({ key, serial: 0, mounted: false });

  useLayoutEffect(() => {
    const current = owner.current;
    current.key = key;
    current.serial += 1;
    current.mounted = true;
    setState(empty<T>(key));
    return () => {
      current.serial += 1;
      current.mounted = false;
    };
  }, [key]);

  const active = (serial: number) => owner.current.mounted
    && owner.current.key === key && owner.current.serial === serial;

  async function run(request: () => Promise<T>): Promise<void> {
    if (!owner.current.mounted || owner.current.key !== key) return;
    const serial = ++owner.current.serial;
    setState({ key, data: null, loading: true, error: "" });
    try {
      const data = await request();
      if (active(serial)) setState({ key, data, loading: false, error: "" });
    } catch (error) {
      if (active(serial)) setState({ key, data: null, loading: false,
        error: error instanceof Error ? error.message : fallbackError });
    }
  }

  function fail(message: string): void {
    if (!owner.current.mounted || owner.current.key !== key) return;
    owner.current.serial += 1;
    setState({ key, data: null, loading: false, error: message });
  }

  // Hide old results during the first render of a changed key, before effects.
  const visible = state.key === key ? state : empty<T>(key);
  return { data: visible.data, loading: visible.loading, error: visible.error, run, fail };
}
