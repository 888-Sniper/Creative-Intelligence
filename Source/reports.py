"""Report exports: one-pager briefs and CSV dumps with lineage footers.

Every export carries the dataset hash plus the cohort definition so any
number can be traced back to its inputs. Client-facing exports render
light-only; no theme state leaks into files.
"""

import csv
import hashlib
import json

from benchmarks import cohort_benchmark, derived, rank_creatives
from creative import recommend

FORMULA_VERSION = "benchmarks-v0"


def dataset_hash(rows):
    """Deterministic sha256 over canonically serialised grain rows."""
    canonical = json.dumps(sorted(rows, key=lambda r: (
        r.get("campaign_id", ""), r.get("creative_id", ""),
        r.get("date", ""))), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def filter_cohort(rows, **criteria):
    return [r for r in rows
            if all(r.get(k) == v for k, v in criteria.items())]


def kpi_totals(rows):
    totals = {"spend": 0.0, "impr": 0.0, "clicks": 0.0, "video_views": 0.0,
              "conversions": 0.0, "revenue": 0.0}
    for row in rows:
        for key in totals:
            totals[key] += row.get(key, 0) or 0
    return derived(dict(totals))


def _fmt(value, places=2):
    return f"{value:.{places}f}"


def one_pager(rows, joined, cohort, cohort_desc, benchmark_metric="cpa"):
    """Build a Markdown executive summary for one cohort."""
    totals = kpi_totals(rows)
    bench = cohort_benchmark(rows, benchmark_metric)
    card = ("above benchmark" if totals.get(benchmark_metric, 0)
            <= bench["stats"]["mean_weighted"]
            else "below benchmark") if bench["status"] == "ok" \
        else "no benchmark (insufficient data)"
    best = rank_creatives(rows, "cpa")[:3]
    worst = rank_creatives(rows, "cpa")[-1:]
    recs = recommend(joined)
    lines = [
        f"# One-Pager — {cohort_desc}",
        "",
        "## Main results",
        f"- Spend {_fmt(totals['spend'])} | Conversions "
        f"{totals['conversions']:.0f} | CPA {_fmt(totals['cpa'])} | "
        f"ROAS {_fmt(totals['roas'])}",
        f"- CPA benchmark ({benchmark_metric}): "
        f"{_fmt(bench['stats']['mean_weighted'])} "
        f"(median {_fmt(bench['stats']['median'])}) — {card}.",
        "",
        "## Best creatives",
    ]
    for row in best:
        lines.append(f"- {row['creative_id']} ({row['platform']}): CPA "
                     f"{_fmt(row.get('cpa', 0))}, spend "
                     f"{_fmt(row.get('spend', 0))}.")
    lines += ["", "## Watch"]
    for row in worst:
        lines.append(f"- {row['creative_id']} ({row['platform']}): CPA "
                     f"{_fmt(row.get('cpa', 0))} — review creative before "
                     f"scaling.")
    lines += ["", "## Key learnings and next steps"]
    for rec in recs:
        lines.append(f"- {rec}")
    lines += [
        "",
        "---",
        f"Dataset {dataset_hash(rows)} | Cohort {json.dumps(cohort, sort_keys=True)} "
        f"| Formulas {FORMULA_VERSION} | Benchmark {bench['status']}.",
    ]
    return "\n".join(lines) + "\n"


def export_csv(rows, path):
    """Full grain dump with derived metrics for Excel handoff."""
    enriched = [derived(dict(r)) for r in rows]
    fields = ["client", "project", "campaign_id", "creative_id", "platform",
              "vertical", "market", "objective", "funnel_stage", "date",
              "spend", "impr", "clicks", "video_views", "conversions",
              "revenue", "cpm", "ctr", "view_rate", "cpa", "roas"]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)
    return path
