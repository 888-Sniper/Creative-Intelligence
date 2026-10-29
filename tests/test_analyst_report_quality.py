"""QI323: report test plans must retain their source creative.

Synthetic pure-report cases only: no database, provider or API runtime.
Rule IDs legitimately repeat across creatives, so a recommendation must
resolve by (finding_id, creative_ids), never by last rule-ID match.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import analyst_chat


def _finding(rule, creative_id, hypothesis, iteration, priority="high"):
    return {
        "finding_id": rule,
        "creative_ids": [creative_id],
        "priority": priority,
        "layer": "stop",
        "primary_signal": "synthetic signal",
        "observed_values": {},
        "benchmark_values": {},
        "confidence_level": "high",
        "confidence_reasons": [],
        "limitations": [],
        "creative_hypothesis": hypothesis,
        "recommended_iteration": iteration,
        "element_to_preserve": "preserve-%s" % creative_id,
        "element_to_change": "change-%s" % creative_id,
        "diagnosis": "",
        "metric_definition_ids": [],
    }


def _creative(key, findings):
    return {"creative_key": key, "metrics": {}, "findings": findings,
            "message_class": "unknown"}


def _analysis(creatives):
    return {"objective": "reach", "scope": "synthetic",
            "dataset_version": "test-v1", "creatives": creatives,
            "cohort_findings": []}


def _tests_markdown(analysis, lang="en"):
    report = analyst_chat.build_analyst_report(
        analysis, lang=lang, sections=["tests"])
    return report["markdown"]


class AnalystReportIdentityTests(unittest.TestCase):
    def test_same_rule_on_two_creatives_keeps_each_plan(self):
        analysis = _analysis([
            _creative("creative-a", [_finding(
                "shared_rule", "creative-a", "Hypothesis A", "Iteration A")]),
            _creative("creative-b", [_finding(
                "shared_rule", "creative-b", "Hypothesis B", "Iteration B")]),
        ])
        md = _tests_markdown(analysis)
        self.assertEqual(md.count("Hypothesis A"), 1)
        self.assertEqual(md.count("Hypothesis B"), 1)
        self.assertIn("creative-a → Iteration A", md)
        self.assertIn("creative-b → Iteration B", md)
        self.assertLess(md.index("Hypothesis A"), md.index("Hypothesis B"))

    def test_reversed_creative_order_still_resolves_by_identity(self):
        analysis = _analysis([
            _creative("creative-b", [_finding(
                "shared_rule", "creative-b", "Hypothesis B", "Iteration B")]),
            _creative("creative-a", [_finding(
                "shared_rule", "creative-a", "Hypothesis A", "Iteration A")]),
        ])
        md = _tests_markdown(analysis)
        self.assertIn("creative-b → Iteration B", md)
        self.assertIn("creative-a → Iteration A", md)
        self.assertLess(md.index("Hypothesis B"), md.index("Hypothesis A"))

    def test_different_rules_on_one_creative_each_resolve(self):
        analysis = _analysis([_creative("creative-a", [
            _finding("rule_one", "creative-a", "Hypothesis One", "Iter One"),
            _finding("rule_two", "creative-a", "Hypothesis Two", "Iter Two"),
        ])])
        md = _tests_markdown(analysis)
        self.assertIn("creative-a → Iter One", md)
        self.assertIn("creative-a → Iter Two", md)

    def test_ambiguous_duplicate_identity_builds_no_plan(self):
        analysis = _analysis([_creative("creative-a", [
            _finding("shared_rule", "creative-a", "Hypothesis First", "I1"),
            _finding("shared_rule", "creative-a", "Hypothesis Second", "I2"),
        ])])
        md = _tests_markdown(analysis)
        self.assertNotIn("Hypothesis First", md)
        self.assertNotIn("Hypothesis Second", md)
        self.assertIn("omitted", md)

    def test_multi_and_empty_creative_ids_resolve_by_exact_identity(self):
        multi = _finding("shared_rule", "creative-a", "Hypothesis Multi",
                         "Iteration Multi")
        multi["creative_ids"] = ["creative-a", "creative-b"]
        empty = _finding("solo_rule", "creative-b", "Hypothesis Empty",
                         "Iteration Empty")
        empty["creative_ids"] = []
        analysis = _analysis([
            _creative("creative-a", [multi]),
            _creative("creative-b", [empty]),
        ])
        md = _tests_markdown(analysis)
        self.assertIn("creative-a → Iteration Multi", md)
        self.assertIn("creative-b → Iteration Empty", md)

    def test_priority_order_and_three_plan_cap_preserved(self):
        analysis = _analysis([
            _creative("creative-a", [_finding(
                "rule_low", "creative-a", "Hypothesis Low", "Iter Low",
                priority="low")]),
            _creative("creative-b", [_finding(
                "rule_high", "creative-b", "Hypothesis High", "Iter High")]),
            _creative("creative-c", [_finding(
                "rule_mid", "creative-c", "Hypothesis Mid", "Iter Mid",
                priority="medium")]),
            _creative("creative-d", [_finding(
                "rule_extra", "creative-d", "Hypothesis Extra", "Iter X",
                priority="exploratory")]),
        ])
        md = _tests_markdown(analysis)
        self.assertLess(md.index("Hypothesis High"), md.index("Hypothesis Mid"))
        self.assertLess(md.index("Hypothesis Mid"), md.index("Hypothesis Low"))
        self.assertNotIn("Hypothesis Extra", md)

    def test_polish_tests_section_keeps_identities(self):
        analysis = _analysis([
            _creative("creative-a", [_finding(
                "shared_rule", "creative-a", "Hypothesis A", "Iteration A")]),
            _creative("creative-b", [_finding(
                "shared_rule", "creative-b", "Hypothesis B", "Iteration B")]),
        ])
        md = _tests_markdown(analysis, lang="pl")
        self.assertIn("Testy (maks. 3)", md)
        self.assertIn("creative-a → Iteration A", md)
        self.assertIn("creative-b → Iteration B", md)


if __name__ == "__main__":
    unittest.main()
