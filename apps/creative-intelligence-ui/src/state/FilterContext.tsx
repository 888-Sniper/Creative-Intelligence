import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

export interface FilterValues {
  client: string;
  project: string;
  campaign: string;
  platform: string;
  vertical: string;
  market: string;
  funnel: string;
  objective: string;
  kpi: string;
  date: string;
  date_from: string;
  date_to: string;
}

export const EMPTY_FILTERS: FilterValues = {
  client: "",
  project: "",
  campaign: "",
  platform: "all",
  vertical: "",
  market: "",
  funnel: "",
  objective: "",
  kpi: "all",
  date: "",
  date_from: "",
  date_to: "",
};

/** Active scope only: non-empty, non-"all" values (legacy parity). */
export function scopeParams(filters: FilterValues): URLSearchParams {
  const params = new URLSearchParams();
  (Object.keys(filters) as (keyof FilterValues)[]).forEach((k) => {
    if (k === "kpi") return;
    const v = filters[k];
    if (v && v !== "all") params.append(k, v);
  });
  return params;
}

interface FilterContextValue {
  filters: FilterValues;
  setFilter: (key: keyof FilterValues, value: string) => void;
  clearFilters: () => void;
  applyPresetDays: (days: number) => void;
  scope: URLSearchParams;
}

const FilterContext = createContext<FilterContextValue | null>(null);

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<FilterValues>(EMPTY_FILTERS);

  const setFilter = useCallback((key: keyof FilterValues, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
  }, []);

  const clearFilters = useCallback(() => setFilters(EMPTY_FILTERS), []);

  const applyPresetDays = useCallback((days: number) => {
    const to = new Date();
    const from = new Date(to.getTime() - (days - 1) * 86400000);
    setFilters((f) => ({ ...f, date: "", date_from: isoDate(from), date_to: isoDate(to) }));
  }, []);

  const scope = useMemo(() => scopeParams(filters), [filters]);
  const value = useMemo(
    () => ({ filters, setFilter, clearFilters, applyPresetDays, scope }),
    [filters, setFilter, clearFilters, applyPresetDays, scope],
  );
  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be used inside FilterProvider");
  return ctx;
}
