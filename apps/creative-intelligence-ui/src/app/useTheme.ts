import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";
export type Theme = "light" | "dark";

const KEY = "ci-theme";
const CHANGE_EVENT = "ci-theme-change";

function publish(mode: ThemeMode): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<ThemeMode>(CHANGE_EVENT, { detail: mode }));
}

/* Light is the default (§5): first-time users and browsers with no
 * explicit saved choice render light. A stored "dark" is preserved —
 * the hook writes the mode on mount, so a legacy stored value cannot
 * be distinguished from a deliberate choice and must not be erased. */
function stored(): ThemeMode {
  try {
    const v = window.localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* private mode: fall through to light */
  }
  return "light";
}

function systemDark(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function resolve(mode: ThemeMode): Theme {
  return mode === "system" ? (systemDark() ? "dark" : "light") : mode;
}

/** Light/dark/system appearance (item 21). The resolved theme drives
 *  data-theme="dark" (legacy parity); the explicit mode persists. */
export function useTheme(): {
  mode: ThemeMode;
  theme: Theme;
  set: (t: ThemeMode) => void;
  toggle: () => void;
} {
  const [mode, setMode] = useState<ThemeMode>(stored);
  const [theme, setTheme] = useState<Theme>(() => resolve(stored()));

  // The header toggle and the Settings select each call this hook.
  // They have to share one mode: otherwise the page can be dark while
  // the select still says Light, and choosing Light does not fire.
  useEffect(() => {
    const onTheme = (event: Event) => {
      const next = (event as CustomEvent<ThemeMode>).detail;
      if (next !== "light" && next !== "dark" && next !== "system") return;
      setMode((prev) => (prev === next ? prev : next));
    };
    window.addEventListener(CHANGE_EVENT, onTheme);
    return () => window.removeEventListener(CHANGE_EVENT, onTheme);
  }, []);

  useEffect(() => {
    const next = resolve(mode);
    setTheme(next);
    document.documentElement.dataset["theme"] = next === "dark" ? "dark" : "";
    try {
      window.localStorage.setItem(KEY, mode);
    } catch {
      /* private mode: theme simply does not persist */
    }
    publish(mode);
    if (mode !== "system" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const dark = query.matches;
      setTheme(dark ? "dark" : "light");
      document.documentElement.dataset["theme"] = dark ? "dark" : "";
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [mode]);

  const toggle = useCallback(() => {
    setMode((m) => (resolve(m) === "dark" ? "light" : "dark"));
  }, []);

  return { mode, theme, set: setMode, toggle };
}
