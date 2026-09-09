"""Dashboard: render a self-contained HTML view from fixture data (stdlib only).

Light/dark theming uses CSS variables: system preference applies on load,
the toggle persists a manual choice in localStorage, and exports stay
light-only. Open the generated file directly in a browser; no server needed.
"""

import html

from benchmarks import cohort_benchmark
from reports import dataset_hash, kpi_totals


def _t(value):
    """Escape a data string for HTML interpolation."""
    return html.escape(str(value), quote=True)

LIGHT = {"bg": "#ffffff", "surface": "#f6f6f4", "text": "#1a1a1a",
         "muted": "#666666", "border": "#e2e2e0", "good": "#1a7f37",
         "bad": "#b42318", "pill": "#eef0ea"}
DARK = {"bg": "#141412", "surface": "#1e1e1c", "text": "#f0efeb",
        "muted": "#a8a7a3", "border": "#33332f", "good": "#4cc38a",
        "bad": "#f97066", "pill": "#26261f"}


def _vars(mapping):
    return "\n".join(f"  --{k}: {v};" for k, v in mapping.items())


def theme_css():
    return f""":root {{
{_vars(LIGHT)}
}}
[data-theme="dark"] {{
{_vars(DARK)}
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
{_vars(DARK)}
  }}
}}"""


def _badge(cpa, bench_mean):
    good = cpa <= bench_mean
    label = "above benchmark" if good else "below benchmark"
    cls = "good" if good else "bad"
    return f'<span class="badge {cls}">{label}</span>'


def render(rows, joined, cohort_desc):
    totals = kpi_totals(rows)
    bench = cohort_benchmark(rows, "cpa")
    mean = bench["stats"]["mean_weighted"]
    digest = dataset_hash(rows)
    cards = []
    for row in sorted(joined, key=lambda r: r.get("cpa", 0)):
        cards.append(
            f'<div class="card"><div class="thumb">{_t(row["creative_id"])}'
            f'<br>{row.get("duration_s", 0):.0f}s · {_t(row.get("hook_type", ""))}'
            f'</div><div class="kpis">CPA {row.get("cpa", 0):.2f} · '
            f'Spend {row.get("spend", 0):.0f} '
            f'{_badge(row.get("cpa", 0), mean)}</div>'
            f'<div class="meta">{_t(row.get("creator_vs_branded", ""))} · '
            f'product {_t(row.get("product_first_visible_s", 0))}s · '
            f'{_t(row.get("cta", ""))}</div></div>')
    compare = []
    for row in sorted(rows, key=lambda r: r.get("creative_id", "")):
        compare.append(
            f'<tr><td>{_t(row["creative_id"])}</td>'
            f'<td>{_t(row["platform"])}</td>'
            f'<td>{row.get("spend", 0):.0f}</td>'
            f'<td>{row.get("cpa", 0):.2f}</td>'
            f'<td>{row.get("roas", 0):.2f}</td></tr>')
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Creative Performance — {_t(cohort_desc)}</title>
<style>
{theme_css()}
body {{ background: var(--bg); color: var(--text);
  font-family: system-ui, sans-serif; margin: 0; }}
header {{ padding: 16px 24px; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center; }}
.kpis {{ display: flex; gap: 16px; padding: 16px 24px; flex-wrap: wrap; }}
.kpi {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px; padding: 16px 24px; }}
.card {{ border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
.thumb {{ background: var(--pill); padding: 28px 12px; text-align: center;
  font-weight: 600; }}
.card .kpis {{ padding: 8px 12px; }}
.meta {{ padding: 0 12px 12px; color: var(--muted); font-size: 13px; }}
.badge {{ border-radius: 999px; padding: 2px 8px; font-size: 12px; }}
.badge.good {{ background: var(--good); color: #fff; }}
.badge.bad {{ background: var(--bad); color: #fff; }}
table {{ margin: 16px 24px; border-collapse: collapse; }}
td, th {{ border: 1px solid var(--border); padding: 6px 10px; font-size: 14px; }}
footer {{ padding: 16px 24px; color: var(--muted); font-size: 12px; }}
button {{ background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; }}
</style>
</head>
<body>
<header><h1>{_t(cohort_desc)}</h1>
<button onclick="toggleTheme()">Toggle light / dark</button></header>
<div class="kpis">
<div class="kpi">Spend {totals['spend']:.2f}</div>
<div class="kpi">CPA {totals['cpa']:.2f}</div>
<div class="kpi">ROAS {totals['roas']:.2f}</div>
<div class="kpi">Benchmark CPA {mean:.2f} ({bench['status']})</div>
</div>
<h2 style="padding:0 24px">Creatives</h2>
<div class="grid">
{''.join(cards)}
</div>
<h2 style="padding:0 24px">Compare</h2>
<table><tr><th>Creative</th><th>Platform</th><th>Spend</th><th>CPA</th>
<th>ROAS</th></tr>
{''.join(compare)}
</table>
<footer>Dataset {digest} · light/dark preference stored locally only.
</footer>
<script>
(function () {{
  var t = localStorage.getItem("cp-theme");
  if (t) {{ document.documentElement.dataset.theme = t; }}
  else if (matchMedia("(prefers-color-scheme: dark)").matches) {{
    document.documentElement.dataset.theme = "dark";
  }}
}})();
function toggleTheme() {{
  var r = document.documentElement;
  var n = r.dataset.theme === "dark" ? "light" : "dark";
  r.dataset.theme = n;
  localStorage.setItem("cp-theme", n);
}}
</script>
</body>
</html>
"""
