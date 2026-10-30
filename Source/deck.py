"""Deck export: client-ready slide HTML from the same grounded data.

Light-only and print-friendly (print to PDF for delivery). Every number
comes from the benchmark/creative modules; the lineage footer matches the
one-pager so the two artifacts always agree.
"""

import html

from benchmarks import cohort_benchmark, rank_creatives
from creative import recommend
from reports import dataset_hash, kpi_totals


def _t(value):
    """Escape a data string for HTML interpolation."""
    return html.escape(str(value), quote=True)


def _cpa(value):
    if value is None:
        return "unavailable"
    return f"{value:.2f}"


def slides(rows, joined, cohort_desc):
    """Return an ordered list of (title, body_html) slide tuples."""
    totals = kpi_totals(rows)
    bench = cohort_benchmark(rows, "cpa")
    best = rank_creatives(rows, "cpa")[:3]
    worst = rank_creatives(rows, "cpa")[-1:]
    recs = recommend(joined)
    mean = bench["stats"]["mean_weighted"]
    if bench["status"] != "ok" or mean is None or totals.get("cpa") is None:
        card = "no benchmark yet" if bench["status"] != "ok" else \
            "no benchmark (weighted mean unavailable)"
    elif totals["cpa"] <= mean:
        card = "above benchmark"
    else:
        card = "below benchmark"
    mean_text = "unavailable" if mean is None else f"{mean:.2f}"
    deck = [
        ("Performance summary",
         f"<p>Spend {totals['spend']:.2f} · CPA {totals['cpa']:.2f} · "
         f"ROAS {totals['roas']:.2f} — {card}.</p>"),
        ("Best creatives",
         "<ul>" + "".join(
             f"<li>{_t(r['creative_id'])} ({_t(r['platform'])}): CPA "
             f"{_cpa(r.get('cpa', 0))}</li>" for r in best) + "</ul>"),
        ("Watch list",
         "<ul>" + "".join(
             f"<li>{_t(r['creative_id'])}: CPA {_cpa(r.get('cpa', 0))} — "
             f"review before scaling.</li>" for r in worst) + "</ul>"),
        ("Benchmarks",
         f"<p>Cohort CPA mean {mean_text}, "
         f"median {bench['stats']['median']:.2f} "
         f"({bench['stats']['creatives']} creatives, "
         f"{bench['stats']['projects']} projects).</p>"),
        ("Creative learnings",
         "<ul>" + "".join(f"<li>{_t(r)}</li>" for r in recs) + "</ul>"),
        ("Recommendations and next steps",
         "<ul><li>Scale the best creatives above.</li>"
         "<li>Brief 3 variations of the winning hook and CTA.</li>"
         "<li>Re-measure against this same benchmark cohort.</li></ul>"),
    ]
    footer = (f"{_t(cohort_desc)} · Dataset {dataset_hash(rows)} · "
              f"Benchmark {bench['status']}.")
    return deck, footer


def render_deck(rows, joined, cohort_desc):
    deck, footer = slides(rows, joined, cohort_desc)
    body = "".join(f'<section class="slide"><h2>{t}</h2>{b}</section>'
                   for t, b in deck)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Client deck — {_t(cohort_desc)}</title>
<style>
body {{ font-family: system-ui, sans-serif; color: #1a1a1a; margin: 0; }}
.slide {{ padding: 48px; page-break-after: always;
  border-bottom: 2px solid #e2e2e0; }}
h1 {{ padding: 48px 48px 0; }}
footer {{ padding: 24px 48px; color: #666; font-size: 12px; }}
</style>
</head>
<body>
<h1>{_t(cohort_desc)}</h1>
{body}
<footer>{footer}</footer>
</body>
</html>
"""
