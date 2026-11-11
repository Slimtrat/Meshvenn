"""Corpus integrity and evaluator controls; native quality uses the real CLI."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from scripts.geometry_diagnostic_corpus.fixtures import build_corpus
from scripts.geometry_diagnostic_corpus.runner import attempt_accounting, checked_path, inputs_for_case, load_manifest, write_evidence
from scripts.geometry_diagnostic_corpus.scoring import localization_sensitivity, score_case, semantic_signature
from scripts.diagnostic_corpus.fixtures import sha256

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

    def test_attempt_provenance_checks_shared_budget_and_keeps_deltas(self):
        # Contract specimens only; this test makes no native quality claim.
        def attempt(resolution, sessions):
            return SimpleNamespace(resolution=resolution, volume=SimpleNamespace(width=resolution),
                views=(), experiments=(), trace=(), pair_comparisons=(),
                report=SimpleNamespace(resolution=SimpleNamespace(width=resolution)),
                provenance=SimpleNamespace(native_sessions_reserved=sessions, native_applications_reserved=4,
                    native_voxel_test_capacity=128, python_work_reserved=1024, completed_experiments=2,
                    native_projection_applications=4, native_elapsed_seconds=.1, elapsed_seconds=.2))
        provenance = SimpleNamespace(resolution=64, attempted_resolutions=(32, 64), native_sessions_reserved=6,
            native_session_budget=24, native_applications_reserved=8, native_application_budget=220,
            native_voxel_test_capacity=256, native_voxel_test_budget=57_671_680, python_work_reserved=2048,
            python_work_budget=8_000_000_000, completed_experiments=4, native_projection_applications=8,
            native_elapsed_seconds=.2, elapsed_seconds=.5, deadline_seconds=15)
        result = SimpleNamespace(attempts=(attempt(32, 3), attempt(64, 3)), requested_resolution=32, actual_resolution=64,
            report=SimpleNamespace(resolution=SimpleNamespace(width=64)), provenance=provenance)
        for field in ("volume", "views", "experiments", "trace", "pair_comparisons"):
            setattr(result, field, getattr(result.attempts[-1], field))
        self.assertTrue(attempt_accounting(result)["passed"])
        result.volume = SimpleNamespace(width=64, tampered=True)
        self.assertFalse(attempt_accounting(result)["passed"])
        result.volume = result.attempts[-1].volume
        provenance.native_sessions_reserved = 3
        self.assertFalse(attempt_accounting(result)["passed"])
        provenance.native_sessions_reserved = 6
        provenance.native_session_budget = 100
        self.assertFalse(attempt_accounting(result)["passed"])

    def test_attempt_artifact_prefix_prevents_overwriting_coarse_result(self):
        # Byte serialization test only; masks are not a quality-evaluation backend.
        def specimen(values):
            volume = SimpleNamespace(values=values, sha256="a" * 64, width=8, depth=8, height=8,
                                     occupied_count=sum(values), bounds=None)
            return SimpleNamespace(volume=volume, views=(), experiments=(), pair_comparisons=())
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as folder:
            destination = Path(folder)
            first = write_evidence(destination, specimen(bytes(512)), prefix="attempt-01-n32-", scope="attempt-01-n32")
            second = write_evidence(destination, specimen(bytes([1]) * 512), prefix="attempt-02-n64-", scope="attempt-02-n64")
            self.assertNotEqual(first[0]["path"], second[0]["path"])
            self.assertEqual((destination / first[0]["path"]).read_bytes(), bytes(512))
            self.assertEqual((destination / second[0]["path"]).read_bytes(), bytes([1]) * 512)

    def test_verify_only_needs_no_native_binary_and_advertises_no_quality(self):
        child = subprocess.run([sys.executable, str(ROOT / "scripts/qualify_geometry_diagnostics.py"), "--verify-only"],
                               capture_output=True, text=True, check=False, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn("No native quality evaluation executed", child.stdout)

    def test_committed_actual_evidence_hashes_and_failed_attempts_are_retained(self):
        document = json.loads((ROOT / "docs/geometry-diagnostic-corpus-baseline.json").read_bytes())
        runs = {run["label"]: run for run in document["runs"]}
        self.assertIn("initial-frozen-evaluation", runs)
        self.assertIn("fresh-ci-binary-pair-regression", runs)
        final = runs["corrected-exact-ci-native-evaluation"]
        self.assertEqual(final["manifest_sha256"], FROZEN_MANIFEST_SHA256)
        self.assertEqual(final["qualification_status"], "fail")
        self.assertEqual({r["case_id"] for r in final["records"] if not r["score"]["passed"]},
                         {"valid_informative_reduction", "healthy_heldout"})
        for run in document["runs"]:
            self.assertEqual(run["manifest_sha256"], FROZEN_MANIFEST_SHA256)
            self.assertTrue(run["authorities_unchanged"])
            for example in run["committed_examples"]:
                directory = ROOT / "docs/geometry-diagnostic-corpus-evidence" / example["name"]
                if example["report_path"] is not None:
                    self.assertEqual(sha256((ROOT / "docs" / example["report_path"]).read_bytes()), example["report_sha256"])
                observation = json.loads((directory / "observation.json").read_bytes())
                for artifact in observation.get("artifacts", []):
                    self.assertEqual(sha256(checked_path(directory, artifact["path"]).read_bytes()), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
