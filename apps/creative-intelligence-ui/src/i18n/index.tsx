/** Locale provider: language state plus locale-aware formatting.
 *
 *  Language is staged in Settings like theme/accent and applied on
 *  Save; this provider holds the APPLIED language. Time-zone-aware
 *  date formatting reads the applied prefs so every surface shares
 *  one clock. Locale formatting (language) and time-zone selection
 *  stay separate preferences: dates render in the UI language but in
 *  the selected IANA zone.
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { isLang, translate, translatePlural, type Lang } from "./core";
import { loadPrefs } from "@/state/prefs";

const LOCALES: Record<Lang, string> = {
  en: "en-US",
  es: "es-ES",
  pl: "pl-PL",
};

export function localeOf(lang: Lang): string {
  return LOCALES[lang];
}

export function languageOf(value: unknown): Lang {
  return isLang(value) ? value : "en";
}

function safeZone(timezone: string): string | undefined {
  if (!timezone) return undefined;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: timezone });
    return timezone;
  } catch {
    return undefined;
  }
}

interface Locale {
  lang: Lang;
  locale: string;
  timezone: string;
  setLang: (lang: Lang) => void;
  setTimezone: (timezone: string) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  tp: (key: string, count: number, vars?: Record<string, string | number>) => string;
  fmtDate: (iso: string, opts?: Intl.DateTimeFormatOptions) => string;
  fmtNum: (n: number, opts?: Intl.NumberFormatOptions) => string;
  fmtPct: (n: number, digits?: number) => string;
  fmtMoney: (n: number, currency?: string) => string;
}

const LocaleContext = createContext<Locale | null>(null);

function parseDate(iso: string): Date | null {
  if (!iso) return null;
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  // Applied language/timezone come from the saved prefs; Settings
  // stages edits separately and commits them here on Save.
  const [lang, setLangState] = useState<Lang>(() => languageOf(loadPrefs().language));
  const [timezone, setTimezoneState] = useState<string>(() => loadPrefs().timezone);

  const setLang = useCallback((next: Lang) => {
    setLangState(isLang(next) ? next : "en");
  }, []);
  const setTimezone = useCallback((next: string) => {
    setTimezoneState(next);
  }, []);

  const value = useMemo<Locale>(() => {
    const locale = LOCALES[lang];
    const zone = safeZone(timezone);
    const t = (key: string, vars?: Record<string, string | number>) =>
      translate(lang, key, vars);
    const tp = (key: string, count: number, vars?: Record<string, string | number>) =>
      translatePlural(lang, key, count, vars);
    const fmtDate = (iso: string, opts?: Intl.DateTimeFormatOptions) => {
      const d = parseDate(iso);
      if (!d) return "—";
      try {
        return new Intl.DateTimeFormat(locale, {
          month: "short",
          day: "numeric",
          year: "numeric",
          ...(zone ? { timeZone: zone } : {}),
          ...opts,
        }).format(d);
      } catch {
        return d.toISOString().slice(0, 10);
      }
    };
    const fmtNum = (n: number, opts?: Intl.NumberFormatOptions) => {
      const v = Number(n);
      if (!Number.isFinite(v)) return "—";
      try {
        return new Intl.NumberFormat(locale, opts).format(v);
      } catch {
        return String(n);
      }
    };
    const fmtPct = (n: number, digits = 1) => {
      const v = Number(n);
      if (!Number.isFinite(v)) return "—";
      try {
        return new Intl.NumberFormat(locale, {
          style: "percent",
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        }).format(v);
      } catch {
        return `${(v * 100).toFixed(digits)}%`;
      }
    };
    const fmtMoney = (n: number, currency = "USD") => {
      const v = Number(n);
      if (!Number.isFinite(v)) return "—";
      try {
        return new Intl.NumberFormat(locale, {
          style: "currency",
          currency,
          maximumFractionDigits: 0,
        }).format(v);
      } catch {
        return `$${v.toFixed(0)}`;
      }
    };
    return { lang, locale, timezone, setLang, setTimezone, t, tp, fmtDate, fmtNum, fmtPct, fmtMoney };
  }, [lang, timezone, setLang, setTimezone]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

const FALLBACK: Locale = {
  lang: "en",
  locale: "en-US",
  timezone: "",
  setLang: () => {},
  setTimezone: () => {},
  t: (key, vars) => translate("en", key, vars),
  tp: (key, count, vars) => translatePlural("en", key, count, vars),
  fmtDate: (iso, opts) => {
    if (!iso) return "—";
    const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
    if (Number.isNaN(d.getTime())) return "—";
    try {
      return new Intl.DateTimeFormat("en-US", {
        month: "short", day: "numeric", year: "numeric", ...opts,
      }).format(d);
    } catch {
      return iso.slice(0, 10);
    }
  },
  fmtNum: (n, opts) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return "—";
    try {
      return new Intl.NumberFormat("en-US", opts).format(v);
    } catch {
      return String(n);
    }
  },
  fmtPct: (n, digits = 1) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return "—";
    return `${(v * 100).toFixed(digits)}%`;
  },
  fmtMoney: (n, currency = "USD") => {
    const v = Number(n);
    if (!Number.isFinite(v)) return "—";
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency", currency, maximumFractionDigits: 0,
      }).format(v);
    } catch {
      return `$${v.toFixed(0)}`;
    }
  },
};

/** Outside a provider (unit tests, isolated renders) this falls back
 *  to English so components stay renderable; the mounted app always
 *  provides the saved language. */
export function useLocale(): Locale {
  return useContext(LocaleContext) ?? FALLBACK;
}
