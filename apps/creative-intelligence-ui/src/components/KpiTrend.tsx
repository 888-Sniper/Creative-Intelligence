import { useEffect, useId, useRef, useState } from "react";
import { useLocale } from "@/i18n";

export type TrendDirection = "up" | "down" | "flat";
export type TrendSentiment = "good" | "bad" | "neutral";
export type TrendState = "compared" | "new" | "none";

export interface KpiComparison {
  percent_change: number | null;
  direction: TrendDirection;
  sentiment: TrendSentiment;
  state: TrendState;
}

export interface KpiPeriod {
  start: string;
  end: string;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Short month name in the UI locale (§9); falls back to the
 *  built-in English abbreviations outside a browser Intl. */
export function monthName(month: number, locale = "en-US"): string {
  if (typeof Intl !== "undefined" && typeof Intl.DateTimeFormat === "function") {
    try {
      const d = new Date(Date.UTC(2024, month - 1, 1));
      const hit = new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" }).format(d);
      if (hit) return hit.replace(/\.$/, "");
    } catch {
      /* fall through to English abbreviations */
    }
  }
  return MONTHS[month - 1] ?? String(month);
}

/** "2023-12-25" -> "Dec 25, 2023" (display only; ISO stays on the wire). */
export function formatDay(iso: string, locale = "en-US"): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return `${monthName(Number(m[2]), locale)} ${Number(m[3])}, ${m[1]}`;
}

/** "Dec 25 – Dec 31, 2023" (year once when shared). Month names
 *  follow the passed UI locale; the default keeps the historic
 *  English output. */
export function formatRange(period: KpiPeriod, locale = "en-US"): string {
  const [sy, sm, sd] = period.start.split("-");
  const [ey, em, ed] = period.end.split("-");
  const startMonth = monthName(Number(sm), locale);
  const endMonth = monthName(Number(em), locale);
  if (sy === ey) {
    return `${startMonth} ${Number(sd)} – ${endMonth} ${Number(ed)}, ${sy}`;
  }
  return `${formatDay(period.start, locale)} – ${formatDay(period.end, locale)}`;
}

const ARROWS: Record<TrendDirection, string> = { up: "↑", down: "↓", flat: "→" };

function signed(pct: number): string {
  const rounded = Math.round(pct * 10) / 10;
  return rounded > 0 ? `+${rounded}%` : `${rounded}%`;
}

export interface KpiTrendProps {
  /** Title Case metric label, e.g. "Impressions". */
  metricLabel: string;
  comparison: KpiComparison;
  /** Null when the backend could not resolve a previous range. */
  previous: KpiPeriod | null;
}

/** Compact period-over-period trend with an accessible info tooltip.

 *  Renders nothing when there is no valid comparison ("none" state),
 *  so no arrow ever appears without real comparison data behind it.
 */
export function KpiTrend({ metricLabel, comparison, previous }: KpiTrendProps) {
  // Locale first: hooks never run conditionally below the early returns.
  const { t, lang } = useLocale();
  // Transient hover/focus state.
  const [open, setOpen] = useState(false);
  // Touch/click-pinned state, independent of focus: a tap pins the
  // tooltip open so a later focus change on touch devices (which can
  // follow the tap or a viewport adjustment) cannot close it. Only a
  // second tap, an outside tap, or Escape unpins.
  const [pinned, setPinned] = useState(false);
  const visible = open || pinned;
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const tipRef = useRef<HTMLSpanElement | null>(null);
  const tipId = useId();
  const { state, direction, sentiment, percent_change: pct } = comparison;

  // Positioning is anchored to the info button itself (buttonRef),
  // never the whole trend row. Desktop is pure CSS (above the icon,
  // centered, 6px gap) with JS collision handling for viewport edges
  // and short viewports. Small screens render the tooltip fixed: pin
  // it to the button in viewport coordinates (flipping above the
  // button near the bottom edge). Reposition on scroll/resize while
  // open: mobile browsers scroll on focus, which can otherwise strand
  // the tooltip at stale coordinates.
  useEffect(() => {
    if (!visible || !tipRef.current) return;
    const tip = tipRef.current;
    if (window.innerWidth <= 900) {
      const place = () => {
        const anchor = buttonRef.current?.getBoundingClientRect();
        if (!anchor) return;
        const height = tip.offsetHeight;
        let top = anchor.bottom + 6;
        if (top + height > window.innerHeight - 8) {
          top = Math.max(8, anchor.top - height - 6);
        }
        tip.style.top = `${Math.round(top)}px`;
      };
      place();
      const raf = requestAnimationFrame(place);
      window.addEventListener("scroll", place, { passive: true, capture: true });
      window.addEventListener("resize", place);
      return () => {
        cancelAnimationFrame(raf);
        window.removeEventListener("scroll", place, { capture: true });
        window.removeEventListener("resize", place);
      };
    }
    // Desktop: the tooltip moves with the page (absolute), so only
    // viewport-edge collisions need correcting. Never tab-specific:
    // everything lives in this shared component.
    tip.style.top = "";
    const adjust = () => {
      const anchor = buttonRef.current?.getBoundingClientRect();
      if (!anchor) return;
      const box = tip.getBoundingClientRect();
      let shift = 0;
      if (box.left < 8) shift = 8 - box.left;
      else if (box.right > window.innerWidth - 8) {
        shift = window.innerWidth - 8 - box.right;
      }
      tip.style.setProperty("--tip-shift", `${Math.round(shift)}px`);
      // Flip below the icon when there is no room above.
      tip.classList.toggle(
        "tip-below",
        anchor.top - tip.offsetHeight - 6 < 8,
      );
    };
    adjust();
    window.addEventListener("resize", adjust);
    return () => window.removeEventListener("resize", adjust);
  }, [visible ]);

  useEffect(() => {
    if (!visible) return;
    const onDown = (e: PointerEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setPinned(false);
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinned(false);
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [visible ]);

  if (state === "none") return null;
  // Defense in depth: the backend sends null (never Infinity/NaN) for
  // every unmeasurable case, but a non-finite value must never reach
  // the DOM even if a payload is ever malformed.
  if (state === "compared" && (pct === null || !Number.isFinite(pct))) return null;

  const locale = lang === "pl" ? "pl-PL" : lang === "es" ? "es-ES" : "en-US";
  const range = previous ? formatRange(previous, locale) : null;
  let tip: string;
  if (state === "new") {
    // The previous window had rows but the metric itself was zero
    // there, so no honest percentage exists.
    tip = range
      ? t("trend.zeroPrevWithRange", { range })
      : t("trend.zeroPrev");
  } else if (direction === "flat") {
    tip = range ? t("trend.flatWithRange", { range })
      : t("trend.flat");
  } else {
    const abs = pct === null ? "" : `${Math.abs(Math.round(pct * 10) / 10)}%`;
    const word = direction === "up" ? t("trend.higher") : t("trend.lower");
    tip = range ? t("trend.deltaWithRange", { metric: metricLabel, abs, word, range })
      : t("trend.delta", { metric: metricLabel, abs, word });
  }

  const shown = state === "new" ? t("trend.isNew") : pct === null ? null : signed(pct);
  if (shown === null) return null;

  return (
    <span
      className={`kpi-trend trend-${sentiment}`}
      ref={wrapRef}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => {
        // A pinned tooltip survives the pointer leaving.
        if (!pinned) setOpen(false);
      }}
    >
      <span aria-hidden="true">{state === "new" ? null : ARROWS[direction]}</span>
      <span>{shown}</span>
      <span className="trend-tooltip-anchor">
        <button
          type="button"
          ref={buttonRef}
          className="trend-info"
          aria-label={t("trend.explain")}
          aria-expanded={visible}
          aria-describedby={visible ? tipId : undefined}
          onClick={(e) => {
            // Keyboard-activated clicks (Enter/Space) carry detail 0:
            // leave the transient focus behavior alone. A real pointer
            // tap/click pins the tooltip open independently of focus, so
            // a later focus change on touch devices cannot close it; a
            // second tap unpins.
            if (e.detail === 0) return;
            if (pinned) {
              setPinned(false);
              setOpen(false);
            } else {
              setPinned(true);
              setOpen(true);
            }
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            // Blur only closes a transient focus tooltip, never a
            // touch/click-pinned one.
            if (!pinned) setOpen(false);
          }}
        >
          <span aria-hidden="true">i</span>
        </button>
        {visible ? (
          <span role="tooltip" id={tipId} className="kpi-tip" ref={tipRef}>
            {tip}
          </span>
        ) : null}
      </span>
    </span>
  );
}
