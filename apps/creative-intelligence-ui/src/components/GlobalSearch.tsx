import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { Icon } from "@/components/icons";

/* Global header search. Searches live backend data across campaigns,
 * creatives, and saved-insight findings and deep-links each hit to its
 * owning page with ?find= applied there. Never fabricates entries:
 * only rows returned by the APIs are shown. */

interface CampaignMetaLite {
  name: string;
  client: string;
}

interface CreativeLite {
  creative_key: string;
  name?: string;
  campaigns?: string[];
}

interface FindingLite {
  creative_key: string;
  name?: string;
  campaign?: string;
  finding?: { primary_signal?: string } | null;
}

interface Hit {
  kind: "campaign" | "creative" | "insight";
  label: string;
  sub: string;
  to: string;
}

const KIND_LABEL: Record<Hit["kind"], string> = {
  campaign: "Campaigns",
  creative: "Creatives",
  insight: "Insights",
};

const LIMITS: Record<Hit["kind"], number> = {
  campaign: 4,
  creative: 4,
  insight: 3,
};

export function GlobalSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [campaigns, setCampaigns] = useState<CampaignMetaLite[] | null>(null);
  const [creatives, setCreatives] = useState<CreativeLite[] | null>(null);
  const [findings, setFindings] = useState<FindingLite[] | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const reqRef = useRef(0);

  /* Load the searchable indexes once the user first types. Cached for
   * the session; failures resolve to empty lists (honest: no dropdown). */
  useEffect(() => {
    const q = query.trim();
    if (!q || campaigns !== null) return;
    const id = ++reqRef.current;
    const done = () => reqRef.current === id;
    void api<{ campaigns: CampaignMetaLite[] }>("GET", "/api/campaigns/meta")
      .then((r) => { if (done()) setCampaigns(r.campaigns ?? []); })
      .catch(() => { if (done()) setCampaigns([]); });
    void api<CreativeLite[]>("GET", "/api/creatives")
      .then((r) => { if (done()) setCreatives(Array.isArray(r) ? r : []); })
      .catch(() => { if (done()) setCreatives([]); });
    void api<{ creatives: FindingLite[] }>("GET", "/api/analyst/creatives?objective=reach")
      .then((r) => { if (done()) setFindings(r.creatives ?? []); })
      .catch(() => { if (done()) setFindings([]); });
  }, [query, campaigns]);

  /* Close on outside click. */
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open ]);

  const hits = useMemo<Hit[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const out: Hit[] = [];
    const push = (kind: Hit["kind"], label: string, sub: string, to: string) => {
      if (out.filter((h) => h.kind === kind).length < LIMITS[kind]) {
        out.push({ kind, label, sub, to });
      }
    };
    for (const c of campaigns ?? []) {
      if (c.name.toLowerCase().includes(q) || c.client.toLowerCase().includes(q)) {
        push("campaign", c.name, c.client, `/campaigns?find=${encodeURIComponent(c.name)}`);
      }
    }
    for (const c of creatives ?? []) {
      const label = c.name || c.creative_key;
      const hay = `${label} ${(c.campaigns ?? []).join(" ")} ${c.creative_key}`.toLowerCase();
      if (hay.includes(q)) {
        push("creative", label, (c.campaigns ?? [])[0] ?? c.creative_key,
          `/creatives?find=${encodeURIComponent(c.creative_key)}`);
      }
    }
    for (const f of findings ?? []) {
      const signal = f.finding?.primary_signal ?? "";
      const hay = `${f.name ?? ""} ${f.campaign ?? ""} ${signal}`.toLowerCase();
      if (signal && hay.includes(q)) {
        push("insight", f.name || f.creative_key, signal.slice(0, 80),
          `/insights?find=${encodeURIComponent(f.name || f.creative_key)}`);
      }
    }
    return out;
  }, [query, campaigns, creatives, findings]);

  const loaded = campaigns !== null && creatives !== null && findings !== null;
  const showDrop = open && query.trim().length > 0;

  const go = (to: string) => {
    setOpen(false);
    setActive(-1);
    setQuery("");
    navigate(to);
  };

  const submitAll = () => {
    const q = query.trim();
    if (q) go(`/campaigns?find=${encodeURIComponent(q)}`);
  };

  return (
    <div className="globalsearch-wrap" ref={boxRef}>
      <form className="globalsearch" role="search"
        onSubmit={(e) => {
          e.preventDefault();
          if (active >= 0 && hits[active]) go(hits[active].to);
          else submitAll();
        }}>
        <Icon name="search" size={17} />
        <input value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(-1); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") { setOpen(false); setActive(-1); }
            else if (e.key === "ArrowDown" && hits.length) {
              e.preventDefault();
              setActive((a) => (a + 1) % hits.length);
            } else if (e.key === "ArrowUp" && hits.length) {
              e.preventDefault();
              setActive((a) => (a - 1 + hits.length) % hits.length);
            }
          }}
          placeholder="Search for campaigns, creatives, or insights…"
          aria-label="Search campaigns, creatives, or insights"
          aria-expanded={showDrop}
          aria-controls="global-search-results"
          role="combobox"
          aria-autocomplete="list"
        />
      </form>
      {showDrop ? (
        <div className="gs-drop" role="listbox" id="global-search-results"
          aria-label="Search suggestions">
          {!loaded ? (
            <p className="gs-empty">Searching…</p>
          ) : hits.length === 0 ? (
            <p className="gs-empty">No Matches for “{query.trim()}”.</p>
          ) : (
            <>
              {(Object.keys(KIND_LABEL) as Array<Hit["kind"]>).map((kind) => {
                const group = hits.filter((h) => h.kind === kind);
                if (!group.length) return null;
                return (
                  <div key={kind}>
                    <p className="gs-group">{KIND_LABEL[kind]}</p>
                    {group.map((h) => {
                      const idx = hits.indexOf(h);
                      return (
                        <button key={`${h.kind}:${h.label}`} type="button" role="option"
                          aria-selected={idx === active}
                          className={`gs-item${idx === active ? " active" : ""}`}
                          onMouseEnter={() => setActive(idx)}
                          onClick={() => go(h.to)}>
                          <Icon name={h.kind === "campaign" ? "campaign" : h.kind === "creative" ? "creatives" : "bookmark"} size={16} />
                          <span className="gs-item-text">
                            <strong>{h.label}</strong>
                            <span>{h.sub}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                );
              })}
              <button type="button" className="gs-all" onClick={submitAll}>
                See all campaign results for “{query.trim()}” →
              </button>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
