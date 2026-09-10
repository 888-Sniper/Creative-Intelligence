import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

function initial(): Theme {
  if (typeof document !== "undefined" && document.documentElement.dataset["theme"] === "dark") return "dark";
  try {
    return window.localStorage.getItem("ci-theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Light/dark appearance (legacy parity: data-theme="dark" + persistence). */
export function useTheme(): { theme: Theme; toggle: () => void; set: (t: Theme) => void } {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => {
    document.documentElement.dataset["theme"] = theme === "dark" ? "dark" : "";
    try {
      window.localStorage.setItem("ci-theme", theme);
    } catch {
      /* private mode: theme simply does not persist */
    }
  }, [theme]);
  return {
    theme,
    toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    set: setTheme,
  };
}
