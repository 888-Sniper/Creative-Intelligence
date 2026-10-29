"""QI270: why-analysis annotation values stay with their owners.

Pairwise and N-way notes must associate hook/format/style, duration,
brand/product timing, CTA, supers, voiceover and structure with the
creative that actually carries each value, in both argument orders.
Synthetic dicts only; no database or provider.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import actions


def _data(cpa, annotation):
    return {
        "spend": 100.0, "impressions": 10000, "clicks": 200,
        "conversions": 10, "cpa": cpa, "ctr": 0.02, "vtr": 0.3,
        "cpc": 0.5, "cpm": 10.0, "roas": 2.0,
        "currency": "USD", "currencies": ["USD"],
        "annotation": annotation,
    }


ANN_A = {
    "hook_type": "problem", "creator_vs_branded": "creator",
    "edit_style": "quick-cut", "duration_s": 30,
    "brand_seconds": [{"start_s": 1}], "product_seconds": [{"start_s": 3}],
    "cta": "Shop now", "supers": ["50% off"],
    "structure": {"voiceover": {"start_s": 0, "end_s": 5},
                  "hook": {"start_s": 0, "end_s": 3}},
}
ANN_B = {
    "hook_type": "offer", "creator_vs_branded": "branded",
    "edit_style": "slow-build", "duration_s": 15,
    "brand_seconds": [{"start_s": 4}], "product_seconds": [],
    "cta": None, "supers": None,
    "structure": {"hook": {"start_s": 0, "end_s": 3}},
}


class WhyAssociationTests(unittest.TestCase):
    def test_pairwise_annotation_values_follow_their_owners(self):
        why = actions._creative_why(
            "cka", "ckb", _data(10.0, ANN_A), _data(20.0, ANN_B))
        text = " ".join(why["differences"])
        self.assertIn("cka uses hook problem while ckb uses offer", text)
        self.assertIn("cka uses format creator while ckb uses branded", text)
        self.assertIn("cka uses style quick-cut while ckb uses slow-build", text)
        self.assertIn("Length: cka runs 30s vs ckb at 15s.", text)
        self.assertIn("Brand appears at 1s in cka vs 4s in ckb.", text)
        self.assertIn("Product appears in cka but has no timing in ckb.", text)
        self.assertIn("CTA is annotated in cka but not in ckb.", text)
        self.assertIn("On-screen supers are annotated in cka but not in ckb.", text)
        self.assertIn("Voiceover is annotated in cka but not in ckb.", text)
        self.assertIn("Structure: cka has voiceover.", text)

    def test_pairwise_associations_reverse_with_argument_order(self):
        why = actions._creative_why(
            "ckb", "cka", _data(20.0, ANN_B), _data(10.0, ANN_A))
        text = " ".join(why["differences"])
        self.assertIn("ckb uses hook offer while cka uses problem", text)
        self.assertIn("Length: ckb runs 15s vs cka at 30s.", text)
        self.assertIn("Brand appears at 4s in ckb vs 1s in cka.", text)
        self.assertIn("Product appears in cka but has no timing in ckb.", text)
        self.assertIn("CTA is annotated in cka but not in ckb.", text)

    def test_multiway_annotation_values_follow_their_owners(self):
        ann_c = {**ANN_A, "hook_type": "problem", "duration_s": 30,
                 "brand_seconds": [], "cta": "Learn more"}
        datas = {
            "cka": _data(10.0, ANN_A),
            "ckb": _data(20.0, ANN_B),
            "ckc": _data(15.0, ann_c),
        }
        why = actions._multi_why(["cka", "ckb", "ckc"], datas)
        text = " ".join(why["differences"])
        self.assertIn("Hook varies: cka=problem; ckb=offer; ckc=problem.", text)
        self.assertIn("Length varies: cka=30s; ckb=15s; ckc=30s.", text)
        self.assertIn(
            "Brand timing is annotated in cka, ckb but not in ckc.", text)
        self.assertIn("CTA is annotated in cka, ckc but not in ckb.", text)


if __name__ == "__main__":
    unittest.main()
