import { useEffect, useId, useRef, useState } from "react";

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

/** "2023-12-25" -> "Dec 25, 2023" (display only; ISO stays on the wire). */
export function formatDay(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[Number(m[2]) - 1] ?? m[2];
  return `${month} ${Number(m[3])}, ${m[1]}`;
}

/** "Dec 25 – Dec 31, 2023" (year once when shared). */
export function formatRange(period: KpiPeriod): string {
  const [sy, sm, sd] = period.start.split("-");
  const [ey, em, ed] = period.end.split("-");
  const startMonth = MONTHS[Number(sm) - 1] ?? sm;
  const endMonth = MONTHS[Number(em) - 1] ?? em;
  if (sy === ey) {
    return `${startMonth} ${Number(sd)} – ${endMonth} ${Number(ed)}, ${sy}`;
  }
  return `${formatDay(period.start)} – ${formatDay(period.end)}`;
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
  // Transient hover/focus state.
  const [open, setOpen] = useState(false);
  // Touch/click-pinned state, independent of focus: a tap pins the
  // tooltip open so a later focus change on touch devices (which can
  // follow the tap or a viewport adjustment) cannot close it. Only a
  // second tap, an outside tap, or Escape unpins.
  const [pinned, setPinned] = useState(false);
  const visible = open || pinned;
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const tipRef = useRef<HTMLSpanElement | null>(null);
  const tipId = useId();
  const { state, direction, sentiment, percent_change: pct } = comparison;

  // Small screens render the tooltip fixed: pin it to the trigger in
  // viewport coordinates (flipping above the trigger near the bottom
  // edge). Plain `top: auto` would resolve against the document and
  // can leave the tooltip far off-screen. Reposition on scroll/resize
  // while open: mobile browsers scroll on focus, which can otherwise
  // strand the tooltip at stale coordinates.
  useEffect(() => {
    if (!visible || !wrapRef.current || !tipRef.current) return;
    if (window.innerWidth > 900) return;
    const place = () => {
      const anchor = wrapRef.current?.getBoundingClientRect();
      const tip = tipRef.current;
      if (!anchor || !tip) return;
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

  const range = previous ? formatRange(previous) : null;
  let tip: string;
  if (state === "new") {
    // The previous window had rows but the metric itself was zero
    // there, so no honest percentage exists.
    tip = range
      ? `No Percentage Comparison Available Because The Previous-Period Value In ${range} Was Zero.`
      : "No Percentage Comparison Available Because The Previous-Period Value Was Zero.";
  } else if (direction === "flat") {
    tip = range ? `No Change Compared With ${range}.`
      : "No Change Compared With The Previous Equivalent Date Range.";
  } else {
    const abs = pct === null ? "" : `${Math.abs(Math.round(pct * 10) / 10)}%`;
    const word = direction === "up" ? "Higher" : "Lower";
    tip = range ? `${metricLabel} ${abs} ${word} Than ${range}.`
      : `${metricLabel} ${abs} ${word} Than The Previous Equivalent Date Range.`;
  }

  const shown = state === "new" ? "New" : pct === null ? null : signed(pct);
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
      <button
        type="button"
        className="trend-info"
        aria-label="Explain Comparison Period"
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
  );
}
