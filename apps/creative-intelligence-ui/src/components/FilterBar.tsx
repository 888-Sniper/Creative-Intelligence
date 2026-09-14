import { useFilters } from "@/state/FilterContext";
import type { FilterValues } from "@/state/FilterContext";
import { useLocale } from "@/i18n";

const KPI_OPTIONS = ["all", "spend", "ctr", "cpc", "cpa", "cpm", "vtr", "view_rate", "roas"];

function TextField({ name, label, placeholder }: { name: keyof FilterValues; label: string; placeholder: string }) {
  const { filters, setFilter } = useFilters();
  const value = filters[name];
  return (
    <label>
      {label}
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => setFilter(name, e.target.value)}
        className={value ? "active" : undefined}
      />
    </label>
  );
}

/** Shared top filter bar. Every analytics view reads this scope; scoped API
 *  calls append it via scopedPath() (legacy filtered_path() parity). */
/** Shared top filter bar (§9): labels follow the UI locale; values
 *  stay API codes. Metric names reuse filters.kpis.*. */
export function FilterBar() {
  const { t } = useLocale();
  const { filters, setFilter, clearFilters, applyPresetDays } = useFilters();
  const kpiLabel = (k: string): string => {
    if (k === "all") return t("filterbar.all");
    if (k === "view_rate") return t("filterbar.playRate");
    if (k === "vtr") return t("filterbar.vtrCompleted");
    const key = `filters.kpis.${k}`;
    const hit = t(key);
    return hit === key ? k.toUpperCase() : hit;
  };
  return (
    <div className="filter-bar">
      <h3>{t("filterbar.title")}</h3>
      <div className="muted" style={{ fontSize: 12 }}>
        {t("filterbar.sub")}
      </div>
      <div className="filter-grid">
        <TextField name="client" label={t("filters.client")} placeholder={t("filters.client")} />
        <TextField name="project" label={t("filters.project")} placeholder={t("filters.project")} />
        <TextField name="campaign" label={t("filters.campaign")} placeholder={t("filters.campaign")} />
        <label>
          {t("filters.platform")}
          <select value={filters.platform} onChange={(e) => setFilter("platform", e.target.value)} className={filters.platform !== "all" ? "active" : undefined}>
            <option value="all">{t("filterbar.all")}</option>
            <option value="meta">Meta</option>
            <option value="tiktok">TikTok</option>
          </select>
        </label>
        <TextField name="vertical" label={t("filters.vertical")} placeholder={t("filters.vertical")} />
        <TextField name="market" label={t("filters.market")} placeholder={t("filters.market")} />
        <TextField name="funnel" label={t("filters.funnel")} placeholder={t("filters.funnel")} />
        <TextField name="objective" label={t("filters.objective")} placeholder={t("filters.objective")} />
        <label>
          {t("filterbar.kpiSort")}
          <select value={filters.kpi} onChange={(e) => setFilter("kpi", e.target.value)} className={filters.kpi !== "all" ? "active" : undefined}>
            {KPI_OPTIONS.map((k) => (
              <option key={k} value={k}>
                {kpiLabel(k)}
              </option>
            ))}
          </select>
        </label>
        <TextField name="date" label={t("filters.dateRange")} placeholder={t("filters.dateRange")} />
        <label>
          {t("filters.from")}
          <input type="date" aria-label={t("filters.fromDate")} value={filters.date_from} onChange={(e) => setFilter("date_from", e.target.value)} className={filters.date_from ? "active" : undefined} />
        </label>
        <label>
          {t("filters.to")}
          <input type="date" aria-label={t("filters.toDate")} value={filters.date_to} onChange={(e) => setFilter("date_to", e.target.value)} className={filters.date_to ? "active" : undefined} />
        </label>
      </div>
      <div style={{ marginTop: 8 }}>
        <span className="muted" style={{ fontSize: 12 }}>
          {t("filterbar.presets")}
        </span>{" "}
        <button type="button" className="secondary" onClick={() => applyPresetDays(7)}>
          {t("filterbar.last7")}
        </button>{" "}
        <button type="button" className="secondary" onClick={() => applyPresetDays(30)}>
          {t("filterbar.last30")}
        </button>{" "}
        <button type="button" className="secondary" onClick={() => applyPresetDays(90)}>
          {t("filterbar.last90")}
        </button>
      </div>
      <div style={{ marginTop: 8 }}>
        <button type="button" className="secondary" onClick={clearFilters}>
          {t("filterbar.clear")}
        </button>
      </div>
    </div>
  );
}
