import { useCallback, useEffect, useState, type SetStateAction } from "react";

interface Selection {
  axis: string;
  initialized: boolean;
  keys: Set<string>;
}
type Rows = ReadonlyArray<{ key: string }> | null;

function reconcile(previous: Selection, axis: string, rows: Rows): Selection {
  const current = previous.axis === axis
    ? previous
    : { axis, initialized: false, keys: new Set<string>() };
  // Pending/failed requests hide selection without erasing same-axis choices.
  if (rows === null) return current;
  const available = new Set(rows.map((row) => row.key));
  if (!current.initialized && available.size >= 2) {
    return { axis, initialized: true, keys: new Set([...available].slice(0, 2)) };
  }
  const keys = new Set([...current.keys].filter((key) => available.has(key)).slice(0, 3));
  return keys.size === current.keys.size && [...keys].every((key) => current.keys.has(key))
    ? current
    : { ...current, keys };
}

/** Pass null until rows belong to the current settled request. */
export function useBenchmarkSelection(axis: string, rows: Rows) {
  const [selection, setSelection] = useState<Selection>(() => ({
    axis, initialized: false, keys: new Set(),
  }));
  useEffect(() => {
    setSelection((previous) => reconcile(previous, axis, rows));
  }, [axis, rows]);

  const setSelected = useCallback((action: SetStateAction<Set<string>>) => {
    if (rows === null) return;
    setSelection((previous) => {
      const current = reconcile(previous, axis, rows);
      const requested = typeof action === "function" ? action(new Set(current.keys)) : action;
      const available = new Set(rows.map((row) => row.key));
      return {
        axis,
        initialized: true,
        keys: new Set([...requested].filter((key) => available.has(key)).slice(0, 3)),
      };
    });
  }, [axis, rows]);

  const selected = rows === null ? new Set<string>() : reconcile(selection, axis, rows).keys;
  return { selected, setSelected };
}
