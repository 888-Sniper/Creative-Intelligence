/** Hand-rolled SVG charts (no new dependencies). Responsive via viewBox. */
import { useLocale } from "@/i18n";

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}
function niceTicks(max: number, count = 5): number[] {
  const step = niceMax(max) / (count - 1);
  return Array.from({ length: count }, (_, i) => step * i);
}
export function fmtAxis(n: number, locale = "en"): string {
  // Axis tick labels through the UI locale; English output matches the
  // previous literals exactly (compact, at most one decimal).
  const abs = Math.abs(n);
  if (abs >= 1_000) {
    try {
      return new Intl.NumberFormat(locale, {
        notation: "compact", maximumFractionDigits: 1,
      }).format(n);
    } catch {
      if (abs >= 1_000_000) return `${+(n / 1_000_000).toFixed(1)}M`;
      return `${+(n / 1_000).toFixed(1)}K`;
    }
  }
  return `${Math.round(n)}`;
}

export interface TrendSeries {
  label: string; color: string; soft: string; points: number[]; axis?: "left" | "right";
}
export function TrendChart({ series, labels, height = 240, ticks = 5 }: {
  series: TrendSeries[]; labels: string[]; height?: number; ticks?: number;
}) {
  const { t, locale } = useLocale();
  const W = 640, H = 240, PL = 40, PB = 24, PT = 8, PR = 40;
  const leftMax = Math.max(1, ...series.filter((s) => (s.axis ?? "left") === "left").flatMap((s) => s.points));
  const rightValues = series.filter((s) => s.axis === "right").flatMap((s) => s.points);
  const rightMax = rightValues.length ? Math.max(1, ...rightValues) : 1;
  const top = niceMax(leftMax);
  const rightTop = niceMax(rightMax);
  const grid = niceTicks(top, ticks);
  const rightGrid = rightValues.length ? niceTicks(rightTop, ticks) : [];
  const n = Math.max(1, ...series.map((s) => s.points.length));
  const x = (i: number) => PL + (i * (W - PL - PR)) / Math.max(1, n - 1);
  const y = (v: number, axis: "left" | "right" = "left") => {
    const ceiling = axis === "right" ? rightTop : top;
    return PT + (H - PT - PB) * (1 - v / ceiling);
  };
  const path = (pts: number[], axis: "left" | "right" = "left") =>
    pts.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v, axis).toFixed(1)}`).join(" ");
  const area = (pts: number[], axis: "left" | "right" = "left") =>
    `${path(pts, axis)}L${x(pts.length - 1).toFixed(1)},${y(0, axis).toFixed(1)}L${x(0).toFixed(1)},${y(0, axis).toFixed(1)}Z`;
  const labelEvery = Math.max(1, Math.ceil(n / 7));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height, display: "block" }}
      role="img" aria-label={t("charts.trend")}>
      {grid.map((g) => (
        <g key={g}>
          <line x1={PL} x2={W - PR} y1={y(g)} y2={y(g)} stroke="#E5EAF1" strokeWidth={1} />
          <text x={PL - 7} y={y(g) + 4} textAnchor="end" fontSize={10.5} fill="#8CA0B5">
            {fmtAxis(g, locale)}
          </text>
        </g>
      ))}
      {rightGrid.map((g) => (
        <text key={`r-${g}`} x={W - PR + 7} y={y(g, "right") + 4} textAnchor="start" fontSize={10.5} fill="#8CA0B5">
          {fmtAxis(g, locale)}
        </text>
      ))}
      {series.map((s) => (
        <g key={s.label}>
          <path d={area(s.points, s.axis ?? "left")} fill={s.soft} opacity={0.55} />
          <path d={path(s.points, s.axis ?? "left")} fill="none" stroke={s.color}
            strokeWidth={2.2} strokeLinejoin="round" strokeLinecap="round" />
        </g>
      ))}
      {labels.filter((_, i) => i % labelEvery === 0).map((lb) => {
        const i = labels.indexOf(lb);
        return (
          <text key={`${lb}-${i}`} x={x(i)} y={H - 7} textAnchor="middle"
            fontSize={10.5} fill="#8CA0B5">{lb}</text>
        );
      })}
    </svg>
  );
}

export function TrendLegend({ series }: { series: TrendSeries[] }) {
  return (
    <div className="legend">
      {series.map((s) => (
        <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>
      ))}
    </div>
  );
}

export interface BarGroup {
  label: string; yours: number; bench: number; suffix?: string;
}
export function GroupBars({ groups, height = 230, format }: {
  groups: BarGroup[]; height?: number;
  format?: (v: number) => string;
}) {
  const { t, locale } = useLocale();
  const W = 560, H = 230, PL = 36, PB = 24, PT = 8, PR = 8;
  const max = Math.max(1, ...groups.flatMap((g) => [g.yours, g.bench]));
  const top = niceMax(max);
  const grid = niceTicks(top, 5);
  const y = (v: number) => PT + (H - PT - PB) * (1 - v / top);
  const slot = (W - PL - PR) / Math.max(1, groups.length);
  const bw = Math.min(30, slot / 4.4);
  const fmt = format ?? ((v: number) => fmtAxis(v, locale));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height, display: "block" }}
      role="img" aria-label={t("charts.bars")}>
      {grid.map((g) => (
        <g key={g}>
          <line x1={PL} x2={W - PR} y1={y(g)} y2={y(g)} stroke="#E5EAF1" strokeWidth={1} />
          <text x={PL - 7} y={y(g) + 4} textAnchor="end" fontSize={10.5} fill="#8CA0B5">
            {fmt(g)}
          </text>
        </g>
      ))}
      {groups.map((g, i) => {
        const cx = PL + slot * (i + 0.5);
        return (
          <g key={g.label}>
            <rect x={cx - bw - 3} y={y(g.yours)} width={bw}
              height={Math.max(1, y(0) - y(g.yours))} rx={3} fill="#0A9183" />
            <rect x={cx + 3} y={y(g.bench)} width={bw}
              height={Math.max(1, y(0) - y(g.bench))} rx={3} fill="#CBD8E6" />
            <text x={cx} y={H - 7} textAnchor="middle" fontSize={10.5} fill="#64748F">
              {g.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function BarLegend({ yours, bench }: { yours: string; bench: string }) {
  return (
    <div className="legend">
      <span><i style={{ background: "#0A9183", borderRadius: 2 }} />{yours}</span>
      <span><i style={{ background: "#CBD8E6", borderRadius: 2 }} />{bench}</span>
    </div>
  );
}

export function RetentionCurve({ points, callout, height = 190 }: {
  points: Array<[number, number]>; callout?: string; height?: number;
}) {
  const { t } = useLocale();
  const W = 300, H = 190, PL = 34, PB = 22, PT = 10, PR = 8;
  const maxX = Math.max(1, ...points.map((p) => p[0]));
  const x = (v: number) => PL + (v / maxX) * (W - PL - PR);
  const y = (v: number) => PT + (H - PT - PB) * (1 - v / 100);
  const line = points.map((p, i) =>
    `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  const area = `${line}L${x(maxX).toFixed(1)},${y(0).toFixed(1)}L${x(0).toFixed(1)},${y(0).toFixed(1)}Z`;
  const grid = [0, 25, 50, 75, 100];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height, display: "block" }}
      role="img" aria-label={t("charts.retention")}>
      {grid.map((g) => (
        <g key={g}>
          <line x1={PL} x2={W - PR} y1={y(g)} y2={y(g)} stroke="#E5EAF1" strokeWidth={1} />
          <text x={PL - 6} y={y(g) + 4} textAnchor="end" fontSize={10} fill="#8CA0B5">
            {g}%
          </text>
        </g>
      ))}
      <path d={area} fill="var(--shell-teal-soft)" opacity={0.8} />
      <path d={line} fill="none" stroke="#0A9183" strokeWidth={2.2}
        strokeLinejoin="round" strokeLinecap="round" />
      {points.length > 1 ? (
        <g>
          <circle cx={x(points[1][0])} cy={y(points[1][1])} r={4.5}
            fill="#fff" stroke="#0A9183" strokeWidth={2.5} />
          {callout ? (
            <text x={x(points[1][0]) + 8} y={y(points[1][1]) - 12}
              fontSize={11} fontWeight={700} fill="#16213A">{callout}</text>
          ) : null}
        </g>
      ) : null}
      <text x={x(0)} y={H - 5} textAnchor="middle" fontSize={10} fill="#8CA0B5">0s</text>
      <text x={x(maxX)} y={H - 5} textAnchor="middle" fontSize={10} fill="#8CA0B5">
        {Math.round(maxX)}s
      </text>
    </svg>
  );
}
