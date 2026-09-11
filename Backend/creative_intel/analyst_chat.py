"""Foap Analyst persistent conversations + deterministic task routing.

The LLM is never in the numeric path: every number comes from the
shared calculation engine (analyst_metrics) via analyze_campaign().
This layer persists owner-scoped conversations, routes analyst
requests (Polish + English, typo-tolerant) to deterministic tasks,
resolves anaphora ("those recommendations", "the previous
headline"), and renders locale-aware answers. Analyst-supplied notes
are labelled as such — rewriting is not verification.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import uuid

from creative_intel import analyst
from creative_intel import analyst_metrics as metrics

PL_DIACRITICS = set("ąćęłńóśźż")

PL_STEMS = ("kreacj", "przetest", "wniosk", "rekomend", "ogranicz",
            "punkt", "naglow", "nagł", "pokaz", "pokaż", "wylicz",
            "kampani", "celem", "promocyjn", "neutraln", "spisa",
            "poprzedni", "analiz", "najlepsz", "najgorsz", "tak samo",
            "obejrz", "tabel", "porown", "porówn", "skroc", "skróc",
            "trzy", "testowac", "testować", "do kazdej", "dla kazdej",
            "wszystkich", "wszystkie", "kolejnej", "kolejna")


def detect_language(text, explicit=None):
    """Analyst's language: explicit choice wins, else Polish signals."""
    if explicit in ("pl", "en"):
        return explicit
    low = (text or "").lower()
    if any(ch in PL_DIACRITICS for ch in low):
        return "pl"
    return "pl" if any(stem in low for stem in PL_STEMS) else "en"


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def route_task(question, history):
    """Route to a deterministic task; anaphora resolved from history.

    Returns (task, args). Tasks: full_analysis, recommendations,
    tests, condense, group_awt, all_watchtime, full_table, headline,
    help. history = list of assistant payload dicts (newest last).
    """
    q = _norm(question)

    def has(*stems):
        return any(s in q for s in stems)

    def last_payload_with(*sections):
        for payload in reversed(history or []):
            if any(payload.get(s) for s in sections):
                return payload
        return None

    if has("naglow", "nagłów", "headline", "napisz mi lepiej"):
        return "headline", {}
    if has("ogranicz", "skroc", "skróc", "condense", "shorter",
           "3 punkt", "trzech punkt", "3 points", "three points"):
        target = "tests" if has("przetest", "testowac", "testować",
                                "co przetest") else "recommendations"
        # "...i tak samo co przetestować" inherits the last limit.
        if has("tak samo"):
            prev = last_payload_with("recommendations", "tests")
            limit = (prev or {}).get("condensed_to")
            return "condense", {"target": "tests", "limit": limit or 3}
        return "condense", {"target": target, "limit": 3}
    if has("tak samo") and has("test", "przetest"):
        prev = last_payload_with("recommendations", "tests")
        return "condense", {"target": "tests",
                            "limit": (prev or {}).get("condensed_to")
                            or 3}
    if (has("rekomendac", "recommendation") or (
            has("wniosk") and has("kolejn", "następn", "next", "campaign",
                                  "kampani"))) and not has(
            "hook", "wylicz", "tabel", "dla kazdej", "dla każdej",
            "kazdej kreacji", "każdej kreacji"):
        notes = "spisa" in q or "moje wnioski" in q
        return "recommendations", {"analyst_notes": notes}
    if has("przetest", "co warto", "what to test", "test plan",
           "testowac", "testować") and not has("tak samo"):
        return "tests", {}
    if has("promocyjn", "neutraln", "promotional", "neutral") and \
            has("watch", "oglad", "ogląd", "czas", "avg", "porown",
                "porówn", "compar"):
        return "group_awt", {}
    if has("watch time", "watchtime", "czas ogladania",
           "czas oglądania") and has("wszystkich", "wszystkie", "all"):
        return "all_watchtime", {}
    if has("wszystkich kreacji", "wszystkie kreacje", "all creatives",
           "pelna tabel", "pełna tabel", "full table", "tabel"):
        return "full_table", {}
    if has("hook", "najlepsz", "najgorsz", "best", "worst", "analiz",
           "wniosk", "kreacj", "campaign", "kampani", "dane"):
        return "full_analysis", {}
    return "help", {}


def fmt_value(value, unit, lang):
    """Locale-aware number: 1,18 s / 30,0% in Polish."""
    if value is None:
        return "—"
    if unit == "percent":
        text = "%.1f%%" % value
    elif unit == "seconds":
        text = "%.2f s" % value
    elif unit == "currency_per_mille":
        text = "%.2f" % value
    elif unit == "currency":
        text = "%.2f" % value
    elif unit == "ratio":
        text = "%.2f" % value
    else:
        text = "%.1f" % value if isinstance(value, float) else str(value)
    if lang == "pl":
        text = text.replace(".", ",")
    return text


def fmt_date(iso, lang):
    try:
        year, month, day = iso.split("-")
        if lang == "pl":
            return "%s.%s.%s" % (day, month, year)
    except (ValueError, AttributeError):
        pass
    return iso or ""


def _metric_text(lang, metric_id, result, analysis=None):
    if result is None or result.get("value") is None:
        state = (result or {}).get("state", "unsupported")
        why = {"unsupported": "brak danych" if lang == "pl"
               else "no data",
               "not_applicable": "nie dotyczy" if lang == "pl"
               else "n/a",
               "missing": "częściowe dane" if lang == "pl"
               else "partial"}.get(state, state)
        return "%s (%s)" % (metric_id, why)
    unit = metrics.METRICS.get(metric_id, {}).get("unit", "")
    return fmt_value(result["value"], unit, lang)


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_conversation(conn, owner_id, title, scope, objective,
                        language):
    conv_id = uuid.uuid4().hex
    now = _utcnow()
    conn.execute(
        "INSERT INTO analyst_conversations (id, owner_employee_id,"
        " title, scope_json, objective, language, dataset_version,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (conv_id, owner_id, title[:120], json.dumps(scope or {}),
         objective, language, "", now, now))
    conn.commit()
    return conv_id


def get_conversation(conn, owner_id, conv_id):
    row = conn.execute(
        "SELECT id, owner_employee_id, title, scope_json, objective,"
        " language, dataset_version, created_at, updated_at"
        " FROM analyst_conversations WHERE id=?", (conv_id,)).fetchone()
    if not row or row[1] != owner_id:
        # Owner mismatch reads as not-found: no existence leak across
        # employees, and one history is never another's context.
        raise ValueError("conversation not found")
    keys = ("id", "owner_employee_id", "title", "scope", "objective",
            "language", "dataset_version", "created_at", "updated_at")
    conv = dict(zip(keys, row))
    try:
        conv["scope"] = json.loads(conv["scope"] or "{}")
    except (ValueError, TypeError):
        conv["scope"] = {}
    return conv


def list_conversations(conn, owner_id):
    rows = conn.execute(
        "SELECT id, title, objective, language, dataset_version,"
        " updated_at FROM analyst_conversations"
        " WHERE owner_employee_id=? ORDER BY updated_at DESC",
        (owner_id,)).fetchall()
    return [{"id": r[0], "title": r[1], "objective": r[2],
             "language": r[3], "dataset_version": r[4],
             "updated_at": r[5]} for r in rows]


def append_message(conn, conv_id, role, kind, body_text, payload=None):
    conn.execute(
        "INSERT INTO analyst_messages (conversation_id, role, kind,"
        " body_text, payload_json, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (conv_id, role, kind, body_text or "",
         json.dumps(payload or {}), _utcnow()))
    conn.execute("UPDATE analyst_conversations SET updated_at=?"
                 " WHERE id=?", (_utcnow(), conv_id))
    conn.commit()


def assistant_history(conn, conv_id):
    rows = conn.execute(
        "SELECT kind, body_text, payload_json FROM analyst_messages"
        " WHERE conversation_id=? AND role='assistant' ORDER BY id",
        (conv_id,)).fetchall()
    out = []
    for kind, body, payload_json in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except (ValueError, TypeError):
            payload = {}
        payload["_kind"] = kind
        payload["_text"] = body or ""
        out.append(payload)
    return out


def _definition_line(lang, metric_id):
    definition = metrics.METRICS.get(metric_id, {})
    display = definition.get("display", {}).get(
        lang, definition.get("display", {}).get("en", metric_id))
    return "%s = %s ÷ %s × 100 (%s)" % (
        display, definition.get("numerator", "?"),
        definition.get("denominator", "?"),
        metrics.DEFINITION_VERSION)


def render_table(analysis, lang, rank_by=None):
    """Complete creative table — every in-scope creative, no subsets."""
    lines = []
    for creative in analysis.get("creatives", []):
        hook = _metric_text(lang, "hook_rate_2s_impr",
                            creative["metrics"].get("hook_rate_2s_impr"))
        awt = _metric_text(lang, "awt_per_view",
                           creative["metrics"].get("awt_per_view"))
        hold = _metric_text(lang, "hold_rate",
                            creative["metrics"].get("hold_rate"))
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            creative["creative_key"], creative.get("name", ""),
            hook, hold, awt, creative.get("message_class",
                                          "unknown")))
    head = ("| creative | ad | 2s hook | hold | AWT | class |"
            if lang == "en" else
            "| kreacja | reklama | hook 2s | hold | AWT | klasa |")
    sep = "|---|---|---|---|---|---|"
    return "\n".join([head, sep] + lines)


def render_best_worst(analysis, lang, rank_by=None):
    ranked = analyst.rank_creatives(analysis, rank_by=rank_by)
    definition = ranked["definition"]
    disp = definition.get("display", {}).get(
        lang, definition.get("display", {}).get("en", ranked["rank_by"]))
    if lang == "pl":
        text = "Ranking według **%s** (%s ÷ %s). " % (
            disp, definition.get("numerator"),
            definition.get("denominator"))
    else:
        text = "Ranked by **%s** (%s ÷ %s). " % (
            disp, definition.get("numerator"),
            definition.get("denominator"))
    if ranked["winner"] is not None:
        unit = definition.get("unit", "")
        val = fmt_value(ranked["winner"]["value"], unit, lang)
        if lang == "pl":
            text += "Najlepsza: **%s** (%s). " % (
                ranked["winner"]["creative_key"], val)
        else:
            text += "Best: **%s** (%s). " % (
                ranked["winner"]["creative_key"], val)
        if len(ranked["table"]) > 1:
            last = ranked["table"][-1]
            val = fmt_value(last["value"], unit, lang)
            if lang == "pl":
                text += "Najsłabsza: **%s** (%s). " % (last[
                    "creative_key"], val)
            else:
                text += "Weakest: **%s** (%s). " % (last[
                    "creative_key"], val)
    else:
        text += ("Brak zwycięzcy: za mało danych." if lang == "pl"
                 else "No winner: insufficient evidence.")
    if ranked["excluded"]:
        reasons = ", ".join("%s (%s)" % (e["creative_key"], e["reason"])
                            for e in ranked["excluded"])
        text += (" Wykluczone: %s." % reasons if lang == "pl"
                 else " Excluded: %s." % reasons)
    return text, ranked


def render_recommendations(recommendations, lang, limit=None):
    items = recommendations if limit is None \
        else recommendations[:limit]
    lines = []
    for i, rec in enumerate(items, 1):
        ev = rec.get("evidence", {})
        lines.append(
            "%d. **%s → %s**\n   %s: %s\n   %s (%s: %s)" % (
                i, rec.get("preserve", ""), rec.get("change", ""),
                "Dowód" if lang == "pl" else "Evidence",
                ev.get("signal", ""),
                "Zmierz" if lang == "pl" else "Measure",
                rec.get("outcome_to_measure", {}).get(
                    "attention", ""),
                "pewność %s" % ev.get("confidence", "")
                if lang == "pl"
                else "confidence %s" % ev.get("confidence", "")))
    return "\n".join(lines), items


def render_tests(plans, lang, limit=None):
    items = plans if limit is None else plans[:limit]
    lines = []
    for i, plan in enumerate(items, 1):
        lines.append(
            "%d. **%s**\n   %s: %s → %s\n   %s: %s | %s: %s" % (
                i, plan.get("hypothesis", ""),
                "Wariant" if lang == "pl" else "Variant",
                plan.get("control_creative", ""),
                plan.get("proposed_variant", ""),
                "Sukces" if lang == "pl" else "Success",
                plan.get("primary_success_metric", ""),
                "Ograniczenia" if lang == "pl" else "Limits",
                "; ".join(plan.get("limitations", [])[:2])))
    return "\n".join(lines), items


def group_awt(conn, analysis, lang):
    """AWT for promotional vs neutral creatives, traceable.

    Groups by resolved message_class (import value, else annotation,
    else unknown). Unknowns list separately — never folded into a
    side silently.
    """
    rows, _scope = analyst.scoped_rows(conn, analysis.get(
        "scope_detail", {}))
    classes = {c["creative_key"]: c.get("message_class", "unknown")
               for c in analysis.get("creatives", [])}
    grouped = {}
    for row in rows:
        grouped.setdefault(
            classes.get(row.get("creative_key") or "", "unknown"),
            []).append(row)
    parts, payload = [], {}
    for name in ("promotional", "neutral", "mixed", "unknown"):
        grows = grouped.get(name, [])
        if not grows:
            continue
        awt, _pct = metrics.awt_per_view(grows)
        keys = sorted({g.get("creative_key") or "" for g in grows}
                      - {""})
        payload[name] = {"awt": awt, "creative_ids": keys,
                         "creative_count": len(keys),
                         "exposure": sum(metrics._num(g, "impressions")
                                         for g in grows)}
        if awt.get("value") is not None:
            parts.append("%s: %s (n=%d, %s)" % (
                name, fmt_value(awt["value"], "seconds", lang),
                len(keys), awt.get("basis", "")))
        else:
            parts.append("%s: %s" % (
                name, "; ".join(awt.get("reasons", ["no data"]))))
    if lang == "pl":
        text = "AVG Watch Time wg klasy przekazu (per view, suma " \
            "czasu ÷ odtworzenia): " + "; ".join(parts) + "."
    else:
        text = "AVG Watch Time by message class (per view): " + \
            "; ".join(parts) + "."
    return text, payload


def render_all_watchtime(analysis, lang):
    lines = []
    for creative in analysis.get("creatives", []):
        awt = creative["metrics"].get("awt_per_view") or {}
        basis = awt.get("basis", "")
        state = awt.get("state", "unsupported")
        lines.append("| %s | %s | %s | %s | %s |" % (
            creative["creative_key"],
            creative.get("message_class", "unknown"),
            fmt_value(awt.get("value"), "seconds", lang), basis,
            state))
    head = ("| creative | class | AWT | basis | state |" if lang == "en"
            else "| kreacja | klasa | AWT | podstawa | stan |")
    return "\n".join([head, "|---|---|---|---|---|"] + lines)


def rewrite_headline(question, analysis, lang):
    """Stylistic headline variants; never stronger than the evidence.

    Uses the analyst's supplied headline only. Measured hook rates
    for the mentioned opening styles attach when annotations cover
    them; otherwise an explicit verify-yourself note.
    """
    original = question.split(":", 1)[1].strip() if ":" in question \
        else question.strip()
    original = original.strip("\"'“”")
    variants = [
        original,
        "%s — wnioski z kampanii" % original if lang == "pl"
        else "%s — campaign learnings" % original,
        original.split(".")[0].strip(),
    ]
    seen, unique = set(), []
    for variant in variants:
        if variant and variant not in seen:
            seen.add(variant)
            unique.append(variant)
    grounding = None
    hook_values = {}
    for creative in analysis.get("creatives", []):
        hook = (creative.get("metrics") or {}).get("hook_rate_2s_impr")
        if hook is not None and hook.get("value") is not None:
            hook_values[creative.get("opening_delivery",
                                     "unknown")] = hook["value"]
    if hook_values:
        grounding = "; ".join("%s: %s" % (
            style, fmt_value(val, "percent", lang))
            for style, val in sorted(hook_values.items()))
    if lang == "pl":
        text = "Propozycje (stylistycznie, bez wzmacniania tezy):\n" + \
            "\n".join("%d. %s" % (i + 1, v)
                      for i, v in enumerate(unique[:3]))
        text += "\nUzasadnienie w danych: %s." % (grounding or
                                                 "brak adnotacji"
                                                 " otwarć — zweryfikuj"
                                                 " w danych")
    else:
        text = "Options (stylistic only, claim unchanged):\n" + \
            "\n".join("%d. %s" % (i + 1, v)
                      for i, v in enumerate(unique[:3]))
        text += "\nGrounded in: %s." % (grounding or
                                       "no opening annotations —"
                                       " verify in data")
    return text, {"original": original, "variants": unique[:3],
                  "grounding": grounding}


REPORT_SECTIONS = ("results", "best_worst", "learnings", "recommendations",
                   "tests", "evidence", "methodology")


def _finding_line(finding, lang):
    signal = finding.get("primary_signal", "")
    observed = finding.get("observed_values", {})
    benchmarks = finding.get("benchmark_values", {})
    obs = ", ".join("%s=%s" % (k, fmt_value(v, "", lang))
                    for k, v in observed.items())
    bench = ", ".join("%s=%s" % (k, fmt_value(v, "", lang))
                      for k, v in benchmarks.items())
    line = "- **%s** (%s: %s" % (signal, "Zaobserwowano" if lang == "pl"
                                 else "Observed", obs or "—")
    if bench:
        line += "; %s: %s" % ("Benchmark" if lang == "pl"
                              else "Benchmark", bench)
    diagnosis = finding.get("diagnosis", "")
    if diagnosis:
        line += "). %s: %s" % ("Diagnoza" if lang == "pl"
                               else "Diagnosis", diagnosis)
    else:
        line += ")"
    limits = finding.get("limitations", []) or []
    if limits:
        line += " [%s: %s]" % ("Ograniczenia" if lang == "pl"
                               else "Limits", "; ".join(limits[:2]))
    return line


def _methodology_lines(analysis, lang):
    seen = {}
    for creative in analysis.get("creatives", []):
        for mid, res in (creative.get("metrics") or {}).items():
            if mid == "exposure":
                continue
            seen.setdefault(res.get("metric_id", mid),
                            res.get("definition_version", ""))
    lines = []
    for mid, version in sorted(seen.items()):
        spec = metrics.METRICS.get(mid, {})
        disp = spec.get("display", {}).get(
            lang, spec.get("display", {}).get("en", mid))
        lines.append("- %s: %s (%s ÷ %s, %s, %s)" % (
            mid, disp, spec.get("numerator"), spec.get("denominator"),
            spec.get("unit"), version or metrics.DEFINITION_VERSION))
    states = ("measured / missing / unsupported / estimated /"
              " not_applicable" if lang == "en" else
              "measured / missing / unsupported / estimated /"
              " not_applicable (puste pole = brak danych, nigdy zero)")
    lines.append("- %s: %s" % ("Data states" if lang == "en" else
                               "Stany danych", states))
    return lines


def build_analyst_report(analysis, lang="en", sections=None,
                         rank_by=None):
    """Sectioned analyst report from one deterministic analysis.

    sections is a subset of REPORT_SECTIONS (default all).
    Recommendations/tests cap at three each. Returns {"markdown",
    "sheets", "meta"} where sheets feeds ooxml.build_xlsx for the
    Excel export; formatting never changes values or ranking.
    """
    lang = "pl" if lang == "pl" else "en"
    wanted = [s for s in (sections or list(REPORT_SECTIONS))
              if s in REPORT_SECTIONS] or list(REPORT_SECTIONS)
    recommendations = analyst.recommendations_from_findings(analysis)
    plans = []
    for rec in recommendations[:3]:
        finding = None
        for creative in analysis.get("creatives", []):
            for cand in creative.get("findings", []):
                if cand.get("finding_id") == rec.get("finding_id"):
                    finding = cand
        if finding is not None:
            plans.append(analyst.test_plan_for_finding(finding, analysis))
    title = ("Raport Foap Analyst" if lang == "pl" else "Foap Analyst report")
    md = ["# %s" % title, "",
          "%s: %s | %s: %s | %s: %s" % (
              "Cel" if lang == "pl" else "Objective",
              analysis.get("objective", "reach"),
              "Zakres" if lang == "pl" else "Scope",
              analysis.get("scope", ""),
              "Dane" if lang == "pl" else "Data",
              analysis.get("dataset_version", "")),
          ""]
    if "results" in wanted:
        md += ["## %s" % ("Wyniki" if lang == "pl" else "Results"), "",
               render_table(analysis, lang, rank_by=rank_by), ""]
    best_text, ranked = render_best_worst(analysis, lang, rank_by=rank_by)
    if "best_worst" in wanted:
        md += ["## %s" % ("Najlepsze / najsłabsze" if lang == "pl"
                          else "Best / weakest"),
               "", best_text, ""]
    if "learnings" in wanted:
        md += ["## %s" % ("Wnioski" if lang == "pl" else "Learnings"), ""]
        cohort = analysis.get("cohort_findings", []) or []
        if cohort:
            md += [_finding_line(f, lang) for f in cohort]
        else:
            md += ["- %s" % ("Brak wniosków kohortowych — za mało danych."
                             if lang == "pl" else
                             "No cohort learnings — insufficient data.")]
        md += [""]
    if "recommendations" in wanted:
        rec_text, _items = render_recommendations(
            recommendations, lang, limit=3)
        md += ["## %s" % ("Rekomendacje (maks. 3)" if lang == "pl"
                          else "Recommendations (max 3)"),
               "", rec_text or "-", ""]
    if "tests" in wanted:
        test_text, _plans = render_tests(plans, lang, limit=3)
        md += ["## %s" % ("Testy (maks. 3)" if lang == "pl"
                          else "Tests (max 3)"),
               "", test_text or "-", ""]
    if "evidence" in wanted:
        md += ["## %s" % ("Dowody" if lang == "pl" else "Evidence"), ""]
        any_evidence = False
        for creative in analysis.get("creatives", []):
            for finding in creative.get("findings", []):
                any_evidence = True
                md.append("**%s**" % creative.get("creative_key", ""))
                md.append(_finding_line(finding, lang))
        if not any_evidence:
            md.append("- %s" % ("Brak" if lang == "pl" else "None"))
        md += [""]
    if "methodology" in wanted:
        md += ["## %s" % ("Metodyka" if lang == "pl" else "Methodology"),
               ""] + _methodology_lines(analysis, lang) + [""]

    def _val(res):
        value = (res or {}).get("value")
        return "" if value is None else value

    def _state(res):
        return (res or {}).get("state", "")

    result_rows = []
    for creative in analysis.get("creatives", []):
        mets = creative.get("metrics") or {}
        result_rows.append([
            creative.get("creative_key", ""),
            _val(mets.get("hook_rate_2s_impr")),
            _state(mets.get("hook_rate_2s_impr")),
            _val(mets.get("hold_rate")),
            _state(mets.get("hold_rate")),
            _val(mets.get("awt_per_view")),
            _state(mets.get("awt_per_view")),
            creative.get("message_class", "unknown")])
    finding_rows = []
    for creative in analysis.get("creatives", []):
        for finding in creative.get("findings", []):
            finding_rows.append([
                creative.get("creative_key", ""),
                finding.get("primary_signal", ""),
                finding.get("diagnosis", ""),
                finding.get("creative_hypothesis", ""),
                finding.get("recommended_iteration", ""),
                finding.get("priority", ""),
                finding.get("confidence_level", ""),
                finding.get("element_to_preserve", ""),
                finding.get("element_to_change", "")])
    sheets = [
        {"name": "Results",
         "header": ["creative", "hook_2s", "hook_2s_state", "hold",
                    "hold_state", "awt", "awt_state", "message_class"],
         "rows": result_rows},
        {"name": "Findings",
         "header": ["creative", "primary_signal", "diagnosis",
                    "creative_hypothesis", "recommended_iteration",
                    "priority", "confidence", "preserve", "change"],
         "rows": finding_rows},
        {"name": "Methodology",
         "header": ["line"],
         "rows": [[line] for line in _methodology_lines(analysis, lang)]},
    ]
    return {"markdown": "\n".join(md), "sheets": sheets,
            "meta": {"objective": analysis.get("objective"),
                     "scope": analysis.get("scope"),
                     "dataset_version": analysis.get("dataset_version"),
                     "rank_by": ranked.get("rank_by"),
                     "winner": (ranked.get("winner") or {}).get(
                         "creative_key") if ranked.get("winner") else None,
                     "sections": wanted, "language": lang}}


def finding_instance_id(conv_id, creative_key, finding):
    """Stable instance id, distinct from the diagnostic rule id.

    The rule id (e.g. "drop_near_transition") names the diagnosis;
    the instance id names one occurrence: conversation + creative +
    rule + dataset version + scope. Two creatives firing the same
    rule, or two conversations over the same data, never share a
    row; re-analysis of the same conversation/scope/data yields the
    same id instead of duplicating.
    """
    basis = json.dumps({
        "conversation": conv_id or "",
        "creative": creative_key or "",
        "rule": finding.get("finding_id", ""),
        "dataset_version": finding.get("dataset_version", ""),
        "scope": finding.get("scope", {}),
    }, sort_keys=True)
    return "f-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def persist_findings(conn, conv_id, analysis):
    """Store proposed findings with scope + dataset version.

    Instances upsert by instance id: a repeated analysis refreshes
    the stored evidence but never resets an accepted/rejected status
    back to proposed, and never steals another conversation's row.
    The in-memory finding dicts are updated in place so the UI calls
    accept/reject against the same instance ids.
    """
    now = _utcnow()
    for creative in analysis.get("creatives", []):
        ckey = creative.get("creative_key", "")
        for finding in creative.get("findings", []):
            finding["rule_id"] = finding.get("finding_id", "")
            finding["finding_id"] = finding_instance_id(
                conv_id, ckey, finding)
            finding["conversation_id"] = conv_id
            conn.execute(
                "INSERT INTO analyst_findings (id,"
                " conversation_id, scope_json, dataset_version,"
                " finding_json, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " scope_json=excluded.scope_json,"
                " dataset_version=excluded.dataset_version,"
                " finding_json=excluded.finding_json,"
                " updated_at=excluded.updated_at",
                (finding["finding_id"], conv_id,
                 json.dumps(finding.get("scope", {})),
                 finding.get("dataset_version", ""),
                 json.dumps(finding), now, now))
    conn.commit()


def _scope_changed_note(old_scope, new_scope, old_dv, new_dv, lang):
    if json.dumps(old_scope or {}, sort_keys=True) == \
            json.dumps(new_scope or {}, sort_keys=True) and \
            old_dv == new_dv:
        return ""
    if lang == "pl":
        return " (zakres lub dane zmienione — liczby przeliczone: %s)" \
            % new_dv
    return " (scope or data changed — recomputed: %s)" % new_dv


def answer_turn(conn, owner_id, question, conversation_id=None,
                scope=None, objective="reach", language=None,
                rank_by=None, max_points=None):
    """One persistent analyst turn: route, compute, render, store.

    Scope/objective changes recompute visibly; the new scope and
    dataset version persist on the conversation. Findings persist as
    proposed with scope + version. Never fabricates: with no matching
    rows the turn explains what is missing instead. max_points caps
    recommendation/test rendering (UI "N points" button); numerical
    facts and qualifications are preserved, never reworded away.
    """
    try:
        max_points = int(max_points)
    except (TypeError, ValueError):
        max_points = None
    if max_points is not None and not 1 <= max_points <= 10:
        max_points = None
    objective = objective if objective in analyst.OBJECTIVES else "reach"
    lang = detect_language(question, language)
    scope = dict(scope or {})
    if conversation_id is not None:
        conv = get_conversation(conn, owner_id, conversation_id)
        old_scope, old_dv = conv["scope"], conv["dataset_version"]
        if scope and scope != old_scope:
            pass  # explicit new filters win; noted below
        elif old_scope:
            scope = old_scope
        if not scope and old_scope:
            scope = old_scope
        conv_id = conv["id"]
        if objective != conv.get("objective"):
            pass  # explicit objective wins per turn
    else:
        conv_id = create_conversation(
            conn, owner_id, (question or "")[:60], scope, objective,
            lang)
        old_scope, old_dv = {}, ""
    append_message(conn, conv_id, "user", "question", question,
                   {"scope": scope, "objective": objective})
    history = assistant_history(conn, conv_id)
    task, args = route_task(question, history)
    analysis = analyst.analyze_campaign(conn, scope, objective)
    note = _scope_changed_note(old_scope, scope, old_dv,
                               analysis.get("dataset_version", ""),
                               lang)
    payload = {"task": task, "scope": analysis.get("scope"),
               "scope_detail": analysis.get("scope_detail"),
               "dataset_version": analysis.get("dataset_version"),
               "objective": objective}
    kind = task
    if analysis.get("empty_reason") and task not in ("help", "headline"):
        if lang == "pl":
            text = "Brak danych w tym zakresie (%s). Wgraj raport " \
                "CSV/XLSX albo poluzuj filtry.%s" % (
                    analysis.get("scope"), note)
        else:
            text = "No rows match this scope (%s). Upload a CSV/XLSX " \
                "report or loosen filters.%s" % (
                    analysis.get("scope"), note)
    elif task == "full_analysis":
        persist_findings(conn, conv_id, analysis)
        table = render_table(analysis, lang)
        verdict, ranked = render_best_worst(analysis, lang, rank_by)
        if lang == "pl":
            count = len(analysis.get("creatives", []))
            noun = "kreacja" if count == 1 else (
                "kreacje" if 2 <= count % 10 <= 4 and
                (count % 100 < 12 or count % 100 > 14) else "kreacji")
            text = "%s\n\n%s\n\n%s\n\nTabela zawiera wszystkie %d " \
                "%s w zakresie.%s" % (
                    _definition_line(lang, ranked["rank_by"]), verdict,
                    table, count, noun, note)
        else:
            text = "%s\n\n%s\n\n%s\n\nTable covers all %d in-scope " \
                "creatives.%s" % (
                    _definition_line(lang, ranked["rank_by"]), verdict,
                    table, len(analysis.get("creatives", [])), note)
        payload.update({"table": table, "ranking": ranked,
                        "analysis": _slim_analysis(analysis)})
    elif task == "recommendations":
        recs = analyst.recommendations_from_findings(analysis)
        analyst_notes = args.get("analyst_notes")
        text, items = render_recommendations(recs, lang,
                                             limit=max_points)
        if analyst_notes:
            prefix = "Twoje wnioski traktuję jako notatki analityka " \
                "(nie jako zweryfikowane fakty). " if lang == "pl" \
                else "Your notes are treated as analyst-provided " \
                "(not verified findings). "
            text = prefix + text
        text += note
        payload.update({"recommendations": items,
                        "analyst_notes": bool(analyst_notes)})
        if max_points is not None:
            payload["condensed_to"] = len(items)
    elif task == "tests":
        recs = analyst.recommendations_from_findings(analysis)
        plans = [analyst.test_plan_for_finding(
            {"finding_id": r["finding_id"],
             "creative_hypothesis": r["iteration"],
             "recommended_iteration": r["iteration"],
             "element_to_change": r["change"],
             "element_to_preserve": r["preserve"],
             "layer": r.get("layer", "hold"), "creative_ids": r["creative_ids"],
             "metric_definition_ids": [],
             "limitations": r["evidence"].get("limitations", [])},
            analysis) for r in recs]
        text, items = render_tests(plans, lang, limit=max_points)
        text += note
        payload.update({"tests": items})
        if max_points is not None:
            payload["condensed_to"] = len(items)
    elif task == "condense":
        target, limit = args.get("target", "recommendations"), \
            max_points or args.get("limit", 3) or 3
        recs = analyst.recommendations_from_findings(analysis)
        if target == "tests":
            plans = [analyst.test_plan_for_finding(
                {"finding_id": r["finding_id"],
                 "creative_hypothesis": r["iteration"],
                 "recommended_iteration": r["iteration"],
                 "element_to_change": r["change"],
                 "element_to_preserve": r["preserve"],
                 "layer": r.get("layer", "hold"), "creative_ids": r["creative_ids"],
                 "metric_definition_ids": [],
                 "limitations": r["evidence"].get("limitations", [])},
                analysis) for r in recs]
            text, items = render_tests(plans, lang, limit)
            payload.update({"tests": items})
        else:
            text, items = render_recommendations(recs, lang, limit)
            payload.update({"recommendations": items})
        payload["condensed_to"] = len(items)
        if lang == "pl":
            text = "W %d punktach (liczby i zastrzeżenia bez zmian):\n" \
                % len(items) + text + note
        else:
            text = "In %d points (numbers and caveats kept):\n" \
                % len(items) + text + note
    elif task == "group_awt":
        text, groups = group_awt(conn, analysis, lang)
        text += note
        payload.update({"group_awt": groups})
    elif task == "all_watchtime":
        text = render_all_watchtime(analysis, lang) + note
        payload.update({"watchtime_table": text})
    elif task == "full_table":
        text = render_table(analysis, lang) + note
        payload.update({"table": text})
    elif task == "headline":
        text, head = rewrite_headline(question, analysis, lang)
        payload.update({"headline": head})
    else:
        if lang == "pl":
            text = "Mogę: policzyć hook rate i metryki, porównać " \
                "kreacje, zarekomendować zmiany i testy, streścić " \
                "do N punktów, przepisać nagłówek, porównać kreacje " \
                "promocyjne z neutralnymi. Zapytaj np. o 2s hook " \
                "rate dla każdej kreacji."
        else:
            text = "I can: compute hook rates and metrics, compare " \
                "creatives, recommend changes and tests, condense to " \
                "N points, rewrite a headline, or compare promotional " \
                "vs neutral creatives."
        payload.update({"help": True})
    append_message(conn, conv_id, "assistant", kind, text, payload)
    conn.execute("UPDATE analyst_conversations SET scope_json=?,"
                 " objective=?, language=?, dataset_version=? WHERE id=?",
                 (json.dumps(scope), objective, lang,
                  analysis.get("dataset_version", ""), conv_id))
    conn.commit()
    answer = _answer_envelope(conn, conv_id, analysis, task, text,
                              lang)
    return {"conversation_id": conv_id, "language": lang, "task": task,
            "text": text, "payload": payload,
            "scope": analysis.get("scope"),
            "scope_snapshot": analysis.get("scope_detail",
                                           analysis.get("scope")),
            "answer": answer,
            "dataset_version": analysis.get("dataset_version"),
            "objective": objective}


FINDING_STATUSES = ("proposed", "accepted", "rejected")


def set_finding_status(conn, owner_id, finding_id, status):
    """Accept/reject a finding (learning history).

    Ownership is checked through the parent conversation: one
    employee can never re-label another's learnings, and rejected
    findings stay stored instead of vanishing.
    """
    if status not in FINDING_STATUSES:
        raise ValueError("status must be one of %s"
                         % (list(FINDING_STATUSES),))
    row = conn.execute("SELECT conversation_id FROM analyst_findings"
                       " WHERE id=?", (finding_id,)).fetchone()
    if not row:
        raise ValueError("finding not found")
    get_conversation(conn, owner_id, row[0])  # owner check, no leak
    conn.execute("UPDATE analyst_findings SET status=?, updated_at=?"
                 " WHERE id=?", (status, _utcnow(), finding_id))
    conn.commit()
    return {"id": finding_id, "status": status}


def _answer_envelope(conn, conv_id, analysis, task, text, lang):
    """Frontend AskResponse.answer: the shared ask/display contract.

    The page renders answer.text/tables/findings_stored/follow_ups/
    warnings (AnalystPage AnalystAnswer); the flat text/payload keys
    stay on the response for older API consumers.
    """
    stored = {r[0]: r[1] for r in conn.execute(
        "SELECT id, status FROM analyst_findings"
        " WHERE conversation_id=?", (conv_id,)).fetchall()}
    findings, warnings, seen_warn = [], [], set()
    for creative in analysis.get("creatives", []):
        ckey = creative.get("creative_key", "")
        for finding in creative.get("findings", []):
            fid = finding.get("finding_id", "")
            findings.append({
                "finding_id": fid,
                "rule_id": finding.get("rule_id", ""),
                "status": stored.get(fid, "proposed"),
                "primary_signal": finding.get("primary_signal"),
                "diagnosis": finding.get("diagnosis"),
                "creative_hypothesis": finding.get(
                    "creative_hypothesis"),
                "recommended_iteration": finding.get(
                    "recommended_iteration"),
                "priority": finding.get("priority"),
                "confidence_level": finding.get("confidence_level"),
                "element_to_preserve": finding.get(
                    "element_to_preserve"),
                "element_to_change": finding.get("element_to_change"),
                "creative_ids": (finding.get("creative_ids")
                                 or ([ckey] if ckey else []))})
            for warn in finding.get("limitations", []) or []:
                if warn and warn not in seen_warn:
                    seen_warn.add(warn)
                    warnings.append(warn)
    tables = []
    if task in ("full_analysis", "full_table") and \
            analysis.get("creatives"):
        header = (["creative", "2s hook", "hold", "AWT", "class"]
                  if lang == "en"
                  else ["kreacja", "hook 2s", "hold", "AWT", "klasa"])
        rows = []
        for creative in analysis.get("creatives", []):
            mets = creative.get("metrics", {}) or {}

            def _val(mid):
                res = mets.get(mid) or {}
                return res.get("value")
            rows.append([creative.get("creative_key", ""),
                         _val("hook_rate_2s_impr"), _val("hold_rate"),
                         _val("awt_per_view"),
                         creative.get("message_class", "unknown")])
        tables.append({"title": None, "columns": header, "rows": rows})
    return {"text": text, "language": lang, "tables": tables,
            "findings_stored": findings, "follow_ups": [],
            "warnings": warnings}


def _slim_analysis(analysis):
    """Conversation-sized analysis: creatives with metric values and
    finding headers (full objects stay in analyst_findings)."""
    slim = []
    for creative in analysis.get("creatives", []):
        slim.append({
            "creative_key": creative["creative_key"],
            "message_class": creative.get("message_class"),
            "findings": [{"finding_id": f["finding_id"],
                          "priority": f["priority"],
                          "signal": f["primary_signal"],
                          "confidence": f["confidence_level"]}
                         for f in creative.get("findings", [])],
            "layers": creative.get("layers", [])})
    return slim
