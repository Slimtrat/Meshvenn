"""Corpus integrity and evaluator controls; native quality uses the real CLI."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.geometry_diagnostic_corpus.fixtures import build_corpus
from scripts.geometry_diagnostic_corpus.runner import checked_path, inputs_for_case, load_manifest
from scripts.geometry_diagnostic_corpus.scoring import localization_sensitivity, score_case, semantic_signature

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/diagnostics/geometry-v1"
FROZEN_MANIFEST_SHA256 = "aea6c48d9ffdfe1c5777291c4f0c82c945cb6fcd44e9a398fa9790ba9eb47a49"


class GeometryCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.digest = load_manifest(CORPUS)
        (ROOT / "tmp").mkdir(exist_ok=True)

    def case(self, name):
        return next(case for case in self.manifest["cases"] if case["case_id"] == name)

    def test_frozen_before_native_evaluation_and_regeneration_identical(self):
        self.assertEqual(self.digest, FROZEN_MANIFEST_SHA256)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as folder:
            build_corpus(Path(folder))
            self.assertEqual(load_manifest(Path(folder))[1], self.digest)

    def test_integrity_includes_original_source_and_pngs(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as folder:
            destination = Path(folder)
            build_corpus(destination)
            source = destination / self.case("healthy")["source"]["path"]
            source.write_bytes(source.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                load_manifest(destination)

    def test_assets_cannot_escape_corpus(self):
        with self.assertRaisesRegex(ValueError, "escapes"):
            checked_path(CORPUS, "../v1/manifest.json")

    def test_heldout_labels_cannot_be_relaxed_in_place(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as folder:
            destination = Path(folder)
            build_corpus(destination)
            manifest = json.loads((destination / "manifest.json").read_bytes())
            manifest["cases"][4]["expected"]["controls"] = []
            (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Frozen geometry manifest changed"):
                load_manifest(destination)

    def test_canonical_is_independent_reference_and_never_observation(self):
        case = self.case("canonical_resolves_pair")
        view_set, inputs, _ = inputs_for_case(CORPUS, case, case["variants"][0], "reverse")
        self.assertEqual(len(view_set.canonical_reference.view_ids), 4)
        self.assertEqual(len([v for v in view_set.views if v.role == "observation"]), 4)
        refs = [v for v in view_set.views if v.role == "reference"]
        target = next(v for v in view_set.views if v.view_id == "front")
        self.assertTrue(all(v.view_id in view_set.canonical_reference.view_ids for v in refs))
        self.assertTrue(all(v.image.sha256 != target.image.sha256 for v in refs))
        self.assertEqual(set(inputs), set(view_set.input_order))

    def test_no_output_engine_cannot_pass_healthy_or_conflict_controls(self):
        for case in self.manifest["cases"]:
            self.assertFalse(score_case(case, {})["passed"], case["case_id"])

    def test_good_global_iou_cannot_hide_small_named_region(self):
        observation = {"views": [{"metrics": {"iou": .999, "important_regions": []}}],
                       "report": {"findings": []}}
        score = score_case(self.case("small_important_region"), observation)
        assertions = {a["name"]: a["passed"] for a in score["assertions"]}
        self.assertTrue(assertions["good_mean_iou"])
        self.assertFalse(assertions["important_region_failure"])
        self.assertFalse(score["passed"])

    def test_calibrated_pair_region_evidence_can_satisfy_region_label(self):
        findings = [{"code": "geometry.cross_view_conflict", "status": "fail", "view_ids": ["front", "back"],
                     "regions": [], "proposed_actions": [], "reason": ""},
                    {"code": "geometry.detail_preservation", "status": "fail", "view_ids": ["back"],
                     "regions": [{"view_id": "back", "label": "identity_flag", "bounds": [.28, .79, .36, .87]}],
                     "proposed_actions": [], "reason": ""}]
        observation = {"views": [{"metrics": {"iou": .99, "important_regions": []}}], "report": {"findings": findings},
                       "pair_comparisons": [{"metrics": {"important_regions": [{"status": "fail", "region": findings[1]["regions"][0]}]}}]}
        score = score_case(self.case("small_important_region"), observation)
        self.assertTrue(score["passed"])
        assertion = next(a for a in score["assertions"] if a["name"] == "important_region_failure")
        self.assertEqual(assertion["evidence_sources"], ["actual_calibrated_antipodal_input_comparison"])

    def test_large_voxel_drop_does_not_itself_satisfy_healthy(self):
        observation = {"occupied_count": 1, "trace": [{"before": 1000, "after": 1, "order_index": 1}]}
        score = score_case(self.case("valid_informative_reduction"), observation)
        assertions = {a["name"]: a["passed"] for a in score["assertions"]}
        self.assertTrue(assertions["large_valid_reduction"])
        self.assertFalse(assertions["no_conflict"])
        self.assertFalse(score["passed"])

    def test_healthy_requires_measurement_for_every_view_not_one_pass(self):
        finding = {"code": "geometry.cross_view_conflict", "status": "pass", "view_ids": ["front"],
                   "proposed_actions": [], "reason": "", "regions": []}
        observation = {"occupied_count": 100, "report": {"findings": [finding]}}
        score = score_case(self.case("healthy"), observation)
        self.assertIn("no_conflict", score["failures"])

    def test_unknown_is_not_measured_conflict_and_mock_is_not_native_rejection(self):
        observation = {"report": {"findings": [{"code": "geometry.cross_view_conflict", "status": "unknown",
                        "proposed_actions": [], "view_ids": [], "reason": "unevaluated"}]}}
        self.assertFalse(score_case(self.case("local_appendage_conflict"), observation)["passed"])
        self.assertFalse(score_case(self.case("real_native_rejection"), {"native_probe": {
            "state": "native_rejected", "dll_api_executed": False, "native_error_code": 2}})["passed"])

    def test_order_comparison_checks_localization_and_actions(self):
        report = {"findings": [{"code": "geometry.attribution", "status": "unknown", "view_ids": ["front"],
                               "regions": [], "proposed_actions": []}]}
        changed = copy.deepcopy(report)
        changed["findings"][0]["view_ids"] = ["back"]
        self.assertNotEqual(semantic_signature(report), semantic_signature(changed))

    def test_resolution_localization_keeps_bounds_and_checks_explicit_tolerance(self):
        finding = {"code": "geometry.detail_preservation", "status": "fail", "view_ids": ["front"],
                   "regions": [{"view_id": "front", "label": "identity_flag", "bounds": [.1, .2, .3, .4]}],
                   "proposed_actions": []}
        record = {"report": {"findings": [finding]}, "views": [{"view_id": "front", "expected": {"width": 128},
                  "resolution_tolerance_pixels": 1, "metrics": {"missing_regions": [], "extraneous_regions": []}}]}
        changed = copy.deepcopy(record)
        changed["report"]["findings"][0]["regions"][0]["bounds"] = [.101, .201, .301, .401]
        result = localization_sensitivity(record, changed)
        self.assertTrue(result["matched_bounds_within_tolerance"])
        self.assertEqual(result["matched_regions"][0]["baseline"][0]["bounds"], [.1, .2, .3, .4])
        changed["report"]["findings"][0]["regions"][0]["bounds"] = [.6, .7, .8, .9]
        self.assertFalse(localization_sensitivity(record, changed)["matched_bounds_within_tolerance"])

    def test_verify_only_needs_no_native_binary_and_advertises_no_quality(self):
        child = subprocess.run([sys.executable, str(ROOT / "scripts/qualify_geometry_diagnostics.py"), "--verify-only"],
                               capture_output=True, text=True, check=False, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn("No native quality evaluation executed", child.stdout)


if __name__ == "__main__":
    unittest.main()
