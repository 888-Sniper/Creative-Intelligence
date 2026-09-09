"""Self-check for the first slice: adapters, derived metrics, benchmarks.

Run:  python3 Source/self_check.py   (from Creative Performance/)
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from benchmarks import cohort_benchmark, derived, rank_creatives
from creative import (best_by_element, early_vs_late, join_metrics,
                      load_annotations, needs_review, recommend, verified)
from reports import dataset_hash, export_csv, filter_cohort, one_pager
from ask import answer
from dashboard import render
from providers import CATALOG, PROVIDER_MODE, cue_cap, race, status
from deck import render_deck, slides
from normalise import (detect_source, ingest_file, map_headers,
                        normalise_row)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# 1. Schema loads and has the four tables.
with open(os.path.join(BASE, "Schema", "Canonical Schema V0.json")) as fh:
    schema = json.load(fh)
check("schema version 0", schema["schema_version"] == "0")
check("four tables present", set(schema) >= {"creative_grain",
      "creative_annotation", "benchmark_cohort", "source_manifest"})

# 2. Fixture loads as canonical rows with derived metrics.
rows = []
with open(os.path.join(BASE, "fixtures", "Sample Dataset.csv")) as fh:
    for raw in csv.DictReader(fh):
        row = {k: (float(v) if k in ("spend", "impr", "clicks",
                                     "video_views", "conversions", "revenue")
                   else v) for k, v in raw.items()}
        rows.append(derived(row))
check("fixture has 8 rows", len(rows) == 8)
check("cpm sane on row 0", abs(rows[0]["cpm"] - 3.0) < 1e-9)
check("roas sane on row 0", abs(rows[0]["roas"] - 4.5) < 1e-9)

# 3. Source detection and header mapping.
meta_headers = ["Campaign Name", "Ad Name", "Amount Spent (EUR)",
                "Impressions", "Link Clicks", "Thruplays", "Purchases"]
check("meta detected", detect_source(meta_headers) == "meta")
mapping, unmapped = map_headers(meta_headers, "meta")
canon = {v for v in mapping.values()}
check("meta maps to spend/impr/clicks/views/conv",
      {"spend", "impr", "clicks", "video_views", "conversions"} <= canon)
check("no unmapped meta headers", unmapped == [])
tiktok_headers = ["Campaign Name", "Ad Name", "Cost", "Impression",
                  "Clicks", "Video Views", "Conversions"]
check("tiktok detected", detect_source(tiktok_headers) == "tiktok")

# 4. Row normalisation coerces numerics and fills defaults.
raw = ["GL-001", "GL-001-A", "120", "40000", "900", "12000", "60"]
mini_map = {0: "campaign_id", 1: "creative_id", 2: "spend", 3: "impr",
            4: "clicks", 5: "video_views", 6: "conversions"}
normed = normalise_row(raw, mini_map)
check("spend coerced to float", normed["spend"] == 120.0)
check("missing revenue defaults 0", normed["revenue"] == 0.0)

# 5. Benchmark: small TikTok cohort is insufficient, pooled fallback used.
tiktok = [r for r in rows if r["platform"] == "tiktok"]
bench = cohort_benchmark(tiktok, "cpa", pooled=rows)
check("small cohort insufficient", bench["status"] == "insufficient")
check("fallback used", bench["fallback_used"] is True)
full = cohort_benchmark(rows, "cpa")
check("full set passes min-n (8 creatives, 4 projects)",
      full["status"] == "ok" and full["fallback_used"] is False)

# 6. Ranking: best CPA first with a spend floor.
ranked = rank_creatives(rows, "cpa", min_spend=50)
check("best cpa first", ranked[0]["creative_id"] == "GL-001-A")
check("below-floor row sinks last",
      ranked[-1]["spend"] < 50)

# 7. Creative annotations load, validate, and gate drafts.
anns = load_annotations(os.path.join(BASE, "fixtures",
                                     "Sample Annotations.csv"))
check("annotations load 8 rows", len(anns) == 8)
check("7 verified creatives", len(verified(anns)) == 7)
review = needs_review(anns)
check("one draft in review (DD-001-A)",
      len(review) == 1 and review[0]["creative_id"] == "DD-001-A")

# 8. Metric join and element analysis on verified rows.
joined = join_metrics(verified(anns), rows)
check("join covers 7 verified", len(joined) == 7)
by_id = {r["creative_id"]: r for r in joined}
check("joined cpa correct", abs(by_id["GL-001-A"]["cpa"] - 2.0) < 1e-9)
timing = early_vs_late(joined)
check("early product beats late",
      timing["early_n"] == 4 and timing["late_n"] == 3
      and timing["early_cpa"] < timing["late_cpa"])
hooks = best_by_element(joined, "hook_type")
check("best hook is text", hooks[0]["value"] == "text")
ctas = best_by_element(joined, "cta")
check("best cta is Shop now", ctas[0]["value"] == "Shop now")
recs = recommend(joined)
check("recommendations mention first-3-seconds product",
      any("first 3 seconds" in r for r in recs))
check("recommendations name best cta",
      any("Shop now" in r for r in recs))

# 9. Report exports: hash, cohort filter, one-pager, CSV dump.
digest = dataset_hash(rows)
check("hash is 64 hex chars",
      len(digest) == 64 and all(c in "0123456789abcdef" for c in digest))
check("hash deterministic", dataset_hash(rows) == digest)
lower = filter_cohort(rows, funnel_stage="lower")
check("cohort filter keeps 7 lower-funnel rows", len(lower) == 7)
check("totals spend 740", abs(sum(r["spend"] for r in rows) - 740.0) < 1e-9)
page = one_pager(rows, joined, {"funnel_stage": "lower"},
                 "Lower funnel — Beauty Spain")
check("one-pager names best creative", "GL-001-A" in page)
check("one-pager carries dataset hash", digest in page)
check("one-pager carries cohort + formulas",
      "funnel_stage" in page and "benchmarks-v0" in page)
check("one-pager has learnings section", "## Key learnings" in page)
import tempfile
tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False).name
export_csv(rows, tmp)
with open(tmp) as fh:
    dumped = fh.read()
check("csv dump has header + 8 rows", dumped.count("\n") == 9
      and "creative_id" in dumped.split("\n")[0] and "GL-002-A" in dumped)

# 10. Grounded Q&A over the joined fixture data.
hooks_a = answer("What hooks are working best for Beauty?", rows, joined)
check("hook answer grounded + cites",
      hooks_a["grounded"] and len(hooks_a["citations"]) > 0
      and "Text" in hooks_a["answer"])
tiktok_a = answer("Which formats perform best on TikTok?", rows, joined)
check("tiktok answer grounded", tiktok_a["grounded"]
      and len(tiktok_a["citations"]) > 0)
funnel_a = answer("What is working best for lower funnel?", rows, joined)
check("funnel answer names best creative",
      funnel_a["grounded"] and "GL-001-A" in funnel_a["answer"])
early_a = answer("Does showing the product earlier improve VTR?",
                 rows, joined)
check("early-product answer says yes with numbers",
      early_a["grounded"] and early_a["answer"].startswith("Yes")
      and "2.31" in early_a["answer"])
split_a = answer("What is different between the top 20% and bottom 20%?",
                 rows, joined)
check("top/bottom answer contrasts hooks",
      split_a["grounded"] and "Top uses" in split_a["answer"])
length_a = answer("What video length is performing best?", rows, joined)
check("length answer favours shorts",
      length_a["grounded"] and "under 15s" in length_a["answer"])
next_a = answer("What should we create next?", rows, joined)
check("next answer is specific",
      next_a["grounded"] and "second 3" in next_a["answer"]
      and "Shop now" in next_a["answer"])
unknown_a = answer("Should we buy radio spots?", rows, joined)
check("unknown topic refused without invention",
      not unknown_a["grounded"] and unknown_a["citations"] == []
      and "Insufficient data" in unknown_a["answer"])

# 11. Dashboard render: theming, cards, badges, lineage.
html = render(rows, joined, "Lower funnel — Beauty Spain")
check("valid html shell",
      html.startswith("<!DOCTYPE html>") and html.rstrip().endswith("</html>"))
check("system preference respected",
      "prefers-color-scheme" in html and "matchMedia" in html)
check("toggle persists choice",
      "toggleTheme" in html and "localStorage" in html
      and "cp-theme" in html)
check("dark tokens present", "#141412" in html and "#4cc38a" in html)
check("all verified creatives rendered",
      all(r["creative_id"] in html for r in joined))
check("benchmark badges present",
      "above benchmark" in html and "below benchmark" in html)
check("kpi header shows spend + benchmark",
      "740.00" in html and "Benchmark CPA" in html)
check("footer carries dataset hash", digest in html)

# 12. Providers: mock default, key hygiene, Active/Fallback, cue caps.
check("mock mode by default", PROVIDER_MODE == "mock")
st = status()
check("status reports configured/missing only",
      set(st.values()) <= {"configured", "missing"})
check("no secret values leak into status",
      not any(len(str(v)) > len("configured") for v in st.values()))
check("catalog covers deepseek/kimi/gemini/gpt/claude",
      {"deepseek", "kimi", "gemini", "openai", "claude"} <= set(CATALOG)
      and all(CATALOG[p]["active"] and CATALOG[p]["fallback"]
              for p in ("deepseek", "kimi", "gemini", "openai", "claude")))
check("mock race never claims live",
      race("hello", [])["live"] is False)
try:
    race("hello", ["openai"], mode="live")
    live_ok = False
except RuntimeError as exc:
    live_ok = "never falls back to mocks" in str(exc)
check("live without keys is unavailable, not mock", live_ok)
check("quiet ids keep smaller cue cap",
      cue_cap("gemini-2.5-flash-lite") == 1024
      and cue_cap("unknown-future-model") == 2048)

# 13. Deck export: six slides, grounded numbers, lineage, light-only.
deck_slides, deck_footer = slides(rows, joined, "Lower funnel — Beauty Spain")
check("deck has six slides", len(deck_slides) == 6)
deck_html = render_deck(rows, joined, "Lower funnel — Beauty Spain")
check("deck names best creative + learnings",
      "GL-001-A" in deck_html and "Creative learnings" in deck_html)
check("deck footer carries hash", digest in deck_html)
check("deck agrees with one-pager totals",
      "740.00" in deck_html and "Benchmarks" in deck_html)
check("deck is light-only", "prefers-color-scheme" not in deck_html
      and "data-theme" not in deck_html)

# 14. End-to-end ingest of the grafted per-source fixtures.
import os as _os
meta = ingest_file(_os.path.join(BASE, "fixtures", "Meta Export Sample.csv"))
check("meta file detected, 5 accepted + 1 quarantined",
      meta["source"] == "meta" and len(meta["rows"]) == 5
      and len(meta["quarantined"]) == 1
      and meta["quarantined"][0]["source_row"] == 7
      and "bad date" in meta["quarantined"][0]["reason"])
check("meta US date coerced to ISO",
      any(r["creative_id"] == "Creator Cut 1"
          and r["date"] == "2026-08-03" for r in meta["rows"]))
check("meta date + revenue mapped",
      meta["rows"][0]["date"] == "2026-08-01"
      and meta["rows"][0]["creative_id"] == "UGC Hook A"
      and meta["rows"][0]["revenue"] == 640.0)
check("meta extras quarantined, not dropped",
      "Currency" in meta["unmapped"] and "Ad Set Name" in meta["unmapped"])
tik = ingest_file(_os.path.join(BASE, "fixtures", "TikTok Export Sample.csv"))
check("tiktok file detected, 5 accepted + 1 quarantined",
      tik["source"] == "tiktok" and len(tik["rows"]) == 5
      and len(tik["quarantined"]) == 1
      and "bad spend" in tik["quarantined"][0]["reason"])
check("tiktok creative + spend mapped",
      tik["rows"][0]["creative_id"] == "Hook A"
      and tik["rows"][0]["spend"] == 88.3)
xls = ingest_file(_os.path.join(BASE, "fixtures", "Excel Sample.csv"))
check("agency excel via generic adapter",
      xls["source"] == "generic" and len(xls["rows"]) == 4
      and xls["rows"][0]["creative_id"] == "Hero Banner")
check("three sources unify to 14 canonical rows + 2 quarantined",
      len(meta["rows"]) + len(tik["rows"]) + len(xls["rows"]) == 14
      and len(meta["quarantined"]) + len(tik["quarantined"])
      + len(xls["quarantined"]) == 2)
check("excel serial date coerced to ISO",
      any(r["date"] == "2023-06-23" for r in xls["rows"]))
check("only the two planted dirty rows quarantined",
      len(meta["quarantined"]) == 1 and len(tik["quarantined"]) == 1
      and xls["quarantined"] == [])

# 15. Validation quarantines bad rows with reasons, keeps the good one.
from normalise import validate_row
bad_csv = _os.path.join(tempfile.gettempdir(), "cp-quarantine-probe.csv")
with open(bad_csv, "w") as fh:
    fh.write("campaign,creative,date,spend,impressions,clicks,"
             "conversions,revenue,video views\n"
             "C1,A1,2026-08-01,10,100,5,1,20,50\n"
             "C1,A2,08/02/2026,10,100,5,1,20,50\n"
             "C1,A3,not-a-date,10,100,5,1,20,50\n"
             "C1,A4,2026-08-01,-5,100,5,1,20,50\n"
             "C1,,2026-08-01,10,100,5,1,20,50\n")
probe = ingest_file(bad_csv)
check("two good rows accepted, three quarantined",
      len(probe["rows"]) == 2 and len(probe["quarantined"]) == 3)
check("US date accepted in probe",
      any(r["creative_id"] == "A2" and r["date"] == "2026-08-02"
          for r in probe["rows"]))
reasons = " ".join(q["reason"] for q in probe["quarantined"])
check("reasons name date, spend, creative",
      "bad date" in reasons and "bad spend" in reasons
      and "missing creative_id" in reasons)
ok, _ = validate_row(probe["rows"][0])
check("accepted row validates", ok)

# 16. Review fixes: escaping, hardening, aggregation, empty input.
evil = dict(joined[0])
evil["creative_id"] = '<img src=x onerror=alert(1)>'
evil_html = render(rows, [evil], 'Cohort <b>bold</b>')
check("dashboard escapes hostile data",
      "&lt;img" in evil_html and "<img src=x" not in evil_html
      and "&lt;b&gt;bold&lt;/b&gt;" in evil_html)
evil_deck = render_deck(rows, [evil], 'Cohort <b>bold</b>')
check("deck escapes hostile cohort title",
      "&lt;b&gt;bold&lt;/b&gt;" in evil_deck
      and "<b>bold</b>" not in evil_deck)
evil_grain = dict(rows[0])
evil_grain["creative_id"] = "<img src=x>"
grain_deck = render_deck([evil_grain], joined, "Cohort")
check("deck escapes hostile grain ids",
      "&lt;img" in grain_deck and "<img src=x" not in grain_deck)
ok_nan, reason_nan = validate_row({**rows[0], "spend": float("nan")})
ok_inf, reason_inf = validate_row({**rows[0], "spend": float("inf")})
check("non-finite spend quarantined",
      not ok_nan and not ok_inf and "bad spend" in reason_nan)
cur = normalise_row(["C9", "A9", "2026-08-01", "$1,200.50", "100",
                     "5", "10", "2", "€50.00"],
                    {0: "campaign_id", 1: "creative_id", 2: "date",
                     3: "spend", 4: "impr", 5: "clicks",
                     6: "video_views", 7: "conversions", 8: "revenue"})
check("currency test row validates", validate_row(cur)[0])
check("currency symbols stripped", cur["spend"] == 1200.5)
extra = dict(rows[0])
extra.update({"date": "2026-08-02", "spend": 60.0, "conversions": 20.0,
              "revenue": 180.0})
agg = join_metrics(verified(anns), rows + [extra])
agg_row = next(r for r in agg if r["creative_id"] == "GL-001-A")
check("multi-day creative aggregates from totals",
      agg_row["spend"] == 180.0
      and abs(agg_row["cpa"] - 180.0 / 80.0) < 1e-9)
empty_csv = _os.path.join(tempfile.gettempdir(), "cp-empty-probe.csv")
with open(empty_csv, "w") as fh:
    fh.write("")
try:
    ingest_file(empty_csv)
    empty_ok = False
except ValueError as exc:
    empty_ok = "no header row" in str(exc)
check("empty file raises, not StopIteration", empty_ok)
head_csv = _os.path.join(tempfile.gettempdir(), "cp-header-probe.csv")
with open(head_csv, "w") as fh:
    fh.write("campaign,creative,date,spend\n")
head_only = ingest_file(head_csv)
check("header-only file yields zero rows, no crash",
      head_only["rows"] == [] and head_only["quarantined"] == [])
try:
    ingest_file(tempfile.gettempdir())
    dir_ok = False
except ValueError:
    dir_ok = True
check("directory path rejected", dir_ok)

# 17. Audit edge tests: hash sensitivity, empty renders, ties, zeros.
mutated = [dict(r) for r in rows]
mutated[0]["spend"] = mutated[0]["spend"] + 1.0
check("hash sensitive to mutation", dataset_hash(mutated) != digest)
empty_html = render([], [], "Empty cohort")
check("dashboard renders empty cohort",
      empty_html.startswith("<!DOCTYPE html>")
      and "Benchmark CPA" in empty_html)
empty_deck = render_deck([], [], "Empty cohort")
check("deck renders empty cohort",
      empty_deck.startswith("<!DOCTYPE html>")
      and "Creative learnings" in empty_deck)
tie_rows = [dict(rows[0]), dict(rows[4])]
tie_rows[0]["creative_id"] = "TIE-A"
tie_rows[1]["creative_id"] = "TIE-B"
tie_ranked = rank_creatives(tie_rows, "cpa")
check("ranking ties keep stable input order",
      [r["creative_id"] for r in tie_ranked] == ["TIE-A", "TIE-B"])
zero = derived({"spend": 0.0, "impr": 0, "clicks": 0, "video_views": 0,
                "conversions": 0, "revenue": 0.0})
check("zero denominators yield zeros, not crash",
      zero["cpm"] == 0.0 and zero["ctr"] == 0.0 and zero["vtr"] == 0.0
      and zero["cpa"] == 0.0 and zero["roas"] == 0.0)
junk = [dict(r, product_first_visible_s=v)
        for r, v in zip(joined, ["soon", None, float("nan"), True])]
junk_timing = early_vs_late(junk)
check("non-numeric seconds excluded, never crash",
      junk_timing["early_n"] == 0 and junk_timing["late_n"] == 0
      and junk_timing["early_cpa"] == 0.0)

failed = [n for n, ok in PASS if not ok]
print(f"\n{len(PASS) - len(failed)}/{len(PASS)} checks passed.")
sys.exit(1 if failed else 0)
