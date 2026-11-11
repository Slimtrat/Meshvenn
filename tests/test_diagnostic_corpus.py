"""Qualify measured D1/D2 behavior and preserve explicit downstream abstentions."""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.diagnostic_contracts import DiagnosticReport
from core.diagnostics_preflight import RasterInput
from core.projection_math import NormalizedPoint, compile_projection, project_normalized_point
from scripts.diagnostic_corpus.evidence import difference_overlay
from scripts.diagnostic_corpus.fixtures import CASES, case_assets, canonical_json, rectangles, sha256, source_boxes
from scripts.diagnostic_corpus.runner import DEFERRED, checked_path, load_manifest, qualification_identity, run_qualification
from scripts.diagnostic_corpus.scoring import score_case

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/diagnostics/v1"


class DiagnosticCorpusManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.manifest_hash = load_manifest(CORPUS)

    def test_all_asset_and_source_hashes_and_provenance_are_verified(self):
        self.assertEqual(len(self.manifest["cases"]), 21)
        self.assertEqual({c["split"] for c in self.manifest["cases"]}, {"calibration", "heldout"})
        self.assertFalse(self.manifest["provenance"]["ai_generated"])
        self.assertEqual(self.manifest["provenance"]["external_assets"], [])
        for case in self.manifest["cases"]:
            self.assertEqual(case["truth"]["kind"], "analytic_synthetic")
            self.assertFalse(case["truth"]["real_world_ground_truth"])
            self.assertFalse(case["canonical_reference"]["human_validated"])
            self.assertEqual({v["resolution"] for v in case["variants"]}, {128, 256})

    def test_recipes_reproduce_committed_bytes_without_random_state(self):
        for case_id in ("healthy", "bounded_shift", "missing_small_part", "intentional_asymmetry"):
            spec = next(s for s in CASES if s.case_id == case_id)
            committed = next(c for c in self.manifest["cases"] if c["case_id"] == case_id)
            variant, files = case_assets(spec, 128)
            self.assertEqual(variant, committed["variants"][0])
            for path, data in files.items():
                self.assertEqual(data, (CORPUS / path).read_bytes())

    def test_cardinal_projection_matches_existing_camera_math(self):
        for angle in (0, 90, 180, 270):
            transform = compile_projection(azimuth_degrees=angle, elevation_degrees=0)
            projected = rectangles(source_boxes(), angle)
            for box, rectangle in zip(source_boxes(), projected):
                _, xmin, xmax, ymin, ymax, zmin, zmax = box
                points = [project_normalized_point(NormalizedPoint(x*2,y*2,z*2), transform)
                          for x in (xmin,xmax) for y in (ymin,ymax) for z in (zmin,zmax)]
                for actual, expected in zip((min(p.u for p in points), max(p.u for p in points),
                                             min(p.v for p in points), max(p.v for p in points)), rectangle[1:]):
                    self.assertAlmostEqual(actual, expected)

    def test_missing_small_part_is_not_claimed_as_d2_semantic_detection(self):
        case = next(c for c in self.manifest["cases"] if c["case_id"] == "missing_small_part")
        front = case["variants"][0]["views"][0]
        self.assertLess(front["mask_occupied_pixels"], front["reference_occupied_pixels"])
        self.assertNotIn("geometry.cross_view_conflict", case["expected"]["required_codes"])
        self.assertIn("alignment.suspected", case["expected"]["forbidden_codes"])

    def test_measured_baseline_preserves_failure_history_and_exact_visual_evidence(self):
        baseline = json.loads((ROOT / "docs/diagnostic-corpus-baseline.json").read_text("utf-8"))
        self.assertEqual(baseline["manifest_sha256"], self.manifest_hash)
        self.assertEqual(baseline["initial"]["qualification_status"], "fail")
        self.assertEqual(baseline["initial"]["metrics"]["missed_findings"], 2)
        self.assertIsNone(baseline["initial"]["implementation"])
        self.assertEqual(baseline["corrected"]["qualification_status"], "pass")
        for proof in baseline["representative_common_reports_and_visual_evidence"]:
            directory = ROOT / "docs" / proof["directory"]
            report_data = (directory / "diagnostic-report.json").read_bytes()
            self.assertEqual(sha256(report_data), proof["report_sha256"])
            report = DiagnosticReport.from_json(report_data.decode("utf-8").strip())
            self.assertNotEqual(report.verification_status.value, "pass")
            self.assertEqual(next(f.status.value for f in report.findings if f.code == "geometry.cross_view_conflict"), "unknown")
            for artifact in proof["artifacts"]:
                self.assertEqual(sha256((directory / artifact["path"]).read_bytes()), artifact["sha256"])

    def test_escaping_asset_path_is_rejected(self):
        with self.assertRaises(ValueError):
            checked_path(CORPUS, "../outside.png")

    def test_tampering_is_not_reported_as_qualification(self):
        temporary_root = ROOT / "tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            destination = Path(directory)
            manifest = json.loads(canonical_json(self.manifest))
            manifest["cases"] = [manifest["cases"][0]]
            case = manifest["cases"][0]
            case["variants"] = [case["variants"][0]]
            paths = [case["truth"]["source_path"]] + [asset["path"] for view in case["variants"][0]["views"] for asset in view["assets"].values()]
            for path in paths:
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((CORPUS / path).read_bytes())
            (destination / "manifest.json").write_bytes(canonical_json(manifest))
            (destination / paths[-1]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "asset changed"):
                load_manifest(destination)


class DiagnosticCorpusScoringTests(unittest.TestCase):
    def test_source_changes_invalidate_qualification_identity(self):
        original = {"source_sha256": {"core.diagnostics_preflight.engine": "1"*64}, "python_version": "3.13.0"}
        changed = {**original, "source_sha256": {"core.diagnostics_preflight.engine": "2"*64}}
        self.assertNotEqual(qualification_identity("a"*64, original, []), qualification_identity("a"*64, changed, []))

    def expected(self):
        return {"required_codes": ["input.empty_mask"], "required_statuses": {"input.empty_mask": "fail"},
                "permitted_codes": [], "forbidden_codes": ["alignment.suspected"], "target_view": "front"}

    def test_passing_finding_cannot_satisfy_expected_failure(self):
        score = score_case(self.expected(), [{"code": "input.empty_mask", "status": "pass", "view_ids": ["front"]}])
        self.assertEqual(score["missed_findings"], 1)
        self.assertFalse(score["passed_expectations"])

    def test_localization_misses_and_unexpected_abstentions_count(self):
        score = score_case(self.expected(), [
            {"code": "input.empty_mask", "status": "fail", "view_ids": ["right"]},
            {"code": "camera.unverified", "status": "unknown", "view_ids": ["front"]},
            {"code": "alignment.suspected", "status": "fail", "view_ids": ["front"]},
        ])
        self.assertEqual(score["missed_findings"], 1)
        self.assertEqual(score["false_positive_findings"], 3)
        self.assertEqual(score["localization_misses"], ["input.empty_mask"])
        self.assertEqual(score["abstained_codes"], ["camera.unverified"])

    def test_empty_output_cannot_pass_known_good_controls(self):
        expected = {**self.expected(), "required_codes": [], "required_statuses": {},
                    "pass_requirements": [{"code": "input.integrity", "view_id": "front"}]}
        score = score_case(expected, [])
        self.assertFalse(score["passed_expectations"])
        self.assertEqual(len(score["missed_control_checks"]), 1)

    def test_overlay_is_the_actual_mask_difference(self):
        raster = RasterInput.from_png_bytes(difference_overlay(bytes((0,1,0,1)), bytes((0,0,1,1)), 2))
        pixels = [tuple(round(value*255) for value in raster.rgba[index:index+4]) for index in range(0,16,4)]
        self.assertEqual(pixels, [(250,250,250,255), (20,130,235,255), (225,55,60,255), (70,80,90,255)])


class DiagnosticCorpusIntegrationTests(unittest.TestCase):
    def test_runner_exception_writes_failed_unknown_report_and_counts_failure(self):
        temporary_root = ROOT / "tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            output = Path(directory)
            with patch("scripts.diagnostic_corpus.runner.analyze_preflight", side_effect=RuntimeError("controlled runner failure")):
                summary = run_qualification(CORPUS, output, selected_cases=("healthy",), resolutions=(128,))
            self.assertEqual(summary["qualification_status"], "fail")
            self.assertEqual(summary["metrics"]["execution_failures"], 1)
            report = DiagnosticReport.from_json((output / summary["cases"][0]["report"]).read_text("utf-8").strip())
            self.assertEqual(report.completion.value, "failed")
            self.assertEqual(report.verification_status.value, "unknown")
            self.assertEqual(next(f.status.value for f in report.findings if f.code == "engine.preflight_execution"), "unknown")

    def test_actual_preflight_reports_overlays_abstention_and_failure_contract(self):
        temporary_root = ROOT / "tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            output = Path(directory)
            summary = run_qualification(CORPUS, output,
                selected_cases=("healthy", "bounded_shift", "local_proportion", "engine_failure_contract"), resolutions=(128,))
            self.assertEqual(summary["qualification_status"], "pass", summary["cases"])
            self.assertFalse(summary["complete_matrix"])
            self.assertTrue(summary["implementation_sources_unchanged_during_run"])
            self.assertIn("core.diagnostics_preflight.engine", summary["implementation"]["source_sha256"])
            self.assertTrue(all(len(digest) == 64 for digest in summary["implementation"]["source_sha256"].values()))
            self.assertEqual(summary["external_services"]["paid_api_cost"], 0)
            self.assertTrue(math.isfinite(summary["latency"]["total_seconds"]) and summary["latency"]["total_seconds"] >= 0)
            self.assertEqual(summary["metrics"]["missed_findings"], 0)
            self.assertEqual(summary["metrics"]["false_positive_findings"], 0)
            for case in summary["cases"]:
                for field in ("latency_seconds", "preflight_latency_seconds", "permutation_latency_seconds"):
                    self.assertTrue(math.isfinite(case[field]) and case[field] >= 0)
                report_path = output / case["report"]
                report = DiagnosticReport.from_json(report_path.read_text("utf-8").strip())
                by_code = {finding.code: finding.status.value for finding in report.findings}
                for _, code, _, _ in DEFERRED:
                    self.assertEqual(by_code[code], "unknown")
                self.assertNotEqual(report.verification_status.value, "pass")
                self.assertTrue(case["d1_roundtrip"])
                for view in report.view_set.views:
                    source = view.camera.verification_evidence
                    if source is not None:
                        self.assertEqual(sha256((report_path.parent / source.uri).read_bytes()), source.sha256)
                self.assertTrue(all(check["same_conclusions_dependencies_and_proposals"] for check in case["order_checks"]))
                for artifact in case["evidence"]:
                    self.assertEqual(sha256((report_path.parent / artifact["path"]).read_bytes()), artifact["sha256"])
                if case["case_id"] == "bounded_shift":
                    self.assertEqual(by_code["alignment.suspected"], "fail")
                    self.assertTrue(case["proposal_observations"]["proposals"])
                    self.assertTrue(any(a["phase"] == "proposed" for a in case["evidence"]))
                if case["case_id"] == "engine_failure_contract":
                    self.assertEqual(report.completion.value, "failed")
                    self.assertEqual(by_code["engine.native_execution"], "unknown")


if __name__ == "__main__":
    unittest.main()
