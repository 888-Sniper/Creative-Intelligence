import { useFilters } from "@/state/FilterContext";
import type { FilterValues } from "@/state/FilterContext";

const KPI_OPTIONS = ["all", "spend", "ctr", "cpc", "cpa", "cpm", "vtr", "view_rate", "roas"];
/** UI copy rule: Title Case option display (values stay API codes). */
const OPTION_LABELS: Record<string, string> = {
  all: "All",
  meta: "Meta",
  tiktok: "TikTok",
  spend: "Spend",
  ctr: "CTR",
  cpc: "CPC",
  cpa: "CPA",
  cpm: "CPM",
  vtr: "VTR (Completed)",
  view_rate: "Play Rate",
  roas: "ROAS",
};
const optionLabel = (k: string): string => OPTION_LABELS[k] ?? k;

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
export function FilterBar() {
  const { filters, setFilter, clearFilters, applyPresetDays } = useFilters();
  return (
    <div className="filter-bar">
      <h3>Filters</h3>
      <div className="muted" style={{ fontSize: 12 }}>
        Every view below respects these filters — they query the canonical dimensions on the server.
      </div>
      <div className="filter-grid">
        <TextField name="client" label="Client" placeholder="client" />
        <TextField name="project" label="Project" placeholder="project" />
        <TextField name="campaign" label="Campaign" placeholder="campaign" />
        <label>
          Platform
          <select value={filters.platform} onChange={(e) => setFilter("platform", e.target.value)} className={filters.platform !== "all" ? "active" : undefined}>
            <option value="all">All</option>
            <option value="meta">Meta</option>
            <option value="tiktok">TikTok</option>
          </select>
        </label>
        <TextField name="vertical" label="Vertical" placeholder="vertical" />
        <TextField name="market" label="Market" placeholder="market" />
        <TextField name="funnel" label="Funnel" placeholder="funnel" />
        <TextField name="objective" label="Objective" placeholder="objective" />
        <label>
          KPI (sort)
          <select value={filters.kpi} onChange={(e) => setFilter("kpi", e.target.value)} className={filters.kpi !== "all" ? "active" : undefined}>
            {KPI_OPTIONS.map((k) => (
              <option key={k} value={k}>
                {optionLabel(k)}
              </option>
            ))}
          </select>
        </label>
        <TextField name="date" label="Date" placeholder="date" />
        <label>
          From
          <input type="date" aria-label="From date" value={filters.date_from} onChange={(e) => setFilter("date_from", e.target.value)} className={filters.date_from ? "active" : undefined} />
        </label>
        <label>
          To
          <input type="date" aria-label="To date" value={filters.date_to} onChange={(e) => setFilter("date_to", e.target.value)} className={filters.date_to ? "active" : undefined} />
        </label>
      </div>
      <div style={{ marginTop: 8 }}>
        <span className="muted" style={{ fontSize: 12 }}>
          Presets:
        </span>{" "}
        <button type="button" className="secondary" onClick={() => applyPresetDays(7)}>
          Last 7 Days
        </button>{" "}
        <button type="button" className="secondary" onClick={() => applyPresetDays(30)}>
          Last 30 Days
        </button>{" "}
        <button type="button" className="secondary" onClick={() => applyPresetDays(90)}>
          Last 90 Days
        </button>
      </div>
      <div style={{ marginTop: 8 }}>
        <button type="button" className="secondary" onClick={clearFilters}>
          Clear Filters
        </button>
      </div>
    </div>
  );
}
