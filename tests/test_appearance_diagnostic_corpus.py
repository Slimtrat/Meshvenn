"""Independent authoring/integrity controls; these do not qualify a D4 engine."""
from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import unittest

from core.diagnostics_preflight import RasterInput
from core.projection_math import NormalizedPoint, compile_projection, project_normalized_point
from scripts.appearance_diagnostic_corpus import FROZEN_MANIFEST_SHA256
from scripts.appearance_diagnostic_corpus.authoring import primary_rays, scene, sha256, triangle_hit
from scripts.appearance_diagnostic_corpus.fixtures import REGIONS, build_corpus, inside_region
from scripts.appearance_diagnostic_corpus.integrity import checked_path, load_manifest
from scripts.appearance_diagnostic_corpus.scoring import score_case

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT/"tests/fixtures/diagnostics/appearance-v1"


class AppearanceAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document, cls.digest = load_manifest(CORPUS)
        (ROOT/"tmp").mkdir(exist_ok=True)

    def case(self, identifier):
        return next(case for case in self.document["cases"] if case["case_id"] == identifier)

    def pixels(self, record):
        raster = RasterInput.from_path(CORPUS/record["path"])
        self.assertFalse(raster.error)
        return raster.rgba

    def test_original_definitions_are_frozen_and_regenerate_identically(self):
        self.assertEqual(self.digest,FROZEN_MANIFEST_SHA256)
        self.assertEqual(len(self.document["cases"]),22)
        with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as folder:
            build_corpus(Path(folder))
            self.assertEqual(load_manifest(Path(folder))[1],self.digest)

    def test_manifest_labels_cannot_be_relaxed_in_place(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as folder:
            destination = Path(folder)
            data = json.loads((CORPUS/"manifest.json").read_bytes())
            data["cases"][1]["expected"]["named_region_status"] = ["pass"]
            (destination/"manifest.json").write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"Frozen appearance manifest changed"):
                load_manifest(destination)
        with self.assertRaisesRegex(ValueError,"escapes"):
            checked_path(CORPUS,"../geometry-v1/manifest.json")

    def test_authored_rays_match_native_camera_convention_independently(self):
        for angle in (0,45,90,180,270):
            transform = compile_projection(azimuth_degrees=angle,elevation_degrees=0)
            for index,(origin,direction) in enumerate(primary_rays(angle,32)):
                if index % 37:
                    continue
                point = tuple(origin[i]+2.7*direction[i] for i in range(3))
                uv = project_normalized_point(NormalizedPoint(*point),transform)
                self.assertAlmostEqual(uv.u,(index%32)/31,places=10)
                self.assertAlmostEqual(uv.v,(index//32)/31,places=10)

    def test_occluded_truth_is_unavailable_not_silently_a_good_comparison(self):
        for identifier, invisible in (("occluded_in_reference","reference"),("occluded_in_target","target")):
            for variant in self.case(identifier)["variants"]:
                other = "target" if invisible=="reference" else "reference"
                self.assertEqual(variant["views"][invisible]["visible_named_region_pixels"],0)
                self.assertGreater(variant["views"][other]["visible_named_region_pixels"],0)
        for variant in self.case("never_observed_region")["variants"]:
            self.assertTrue(all(view["visible_named_region_pixels"]==0 for view in variant["views"].values()))

    def test_healthy_shared_region_has_support_and_is_unaffected_by_injection(self):
        for identifier in ("healthy_multicolour","healthy_reprojected"):
            for variant in self.case(identifier)["variants"]:
                self.assertTrue(all(view["visible_named_region_pixels"]>=16 for view in variant["views"].values()))
        a,b = REGIONS["shared_patch"],REGIONS["colour_patch"]
        self.assertTrue(a["x"][0] > b["x"][1])

    def test_declared_gain_is_distinct_from_unknown_lighting_despite_equal_pixels(self):
        controlled = self.case("controlled_neutral_gain")["variants"][0]["views"]["target"]
        lit = self.case("uncontrolled_lighting")["variants"][0]["views"]["target"]
        self.assertEqual(self.pixels(controlled),self.pixels(lit))
        self.assertEqual(controlled["appearance_settings"]["photometry"],"calibrated")
        self.assertEqual(controlled["appearance_settings"]["linear_gain"],.65)
        self.assertEqual(lit["appearance_settings"]["photometry"],"lit")
        self.assertEqual(lit["appearance_settings"]["linear_gain"],1.)

    def test_design_ancestor_and_target_derived_reference_have_opposite_lineage(self):
        accepted = self.case("canonical_ancestor_allowed")["variants"][0]["views"]
        rejected = self.case("reference_from_target")["variants"][0]["views"]
        self.assertEqual(accepted["target"]["lineage"]["derived_from"],[accepted["reference"]["sha256"]])
        self.assertEqual(rejected["reference"]["lineage"]["derived_from"],[rejected["target"]["sha256"]])
        self.assertNotEqual(accepted["target"]["sha256"],accepted["reference"]["sha256"])
        for view in self.case("stale_source")["variants"][0]["views"].values():
            self.assertEqual(sha256((CORPUS/view["path"]).read_bytes()),view["sha256"])
        target = self.case("stale_source")["variants"][0]["views"]["target"]
        self.assertNotEqual(target["declared_content_sha256"],target["sha256"])

    def test_ambiguous_surface_is_true_coincident_geometry_not_only_a_shared_edge(self):
        mesh = scene(ambiguous=True)
        hits = []
        for index,triangle in enumerate(mesh["triangles"]):
            result = triangle_hit((-.4,-3.,-.2),(0.,1.,0.),*(mesh["vertices"][i] for i in triangle))
            if result is not None and abs(result[0]-2.65)<1e-9:
                hits.append(mesh["triangle_labels"][index])
        self.assertIn("body_front",hits)
        self.assertIn("coincident_independent_front",hits)

    def test_mock_cases_and_preview_cannot_claim_human_or_semantic_validation(self):
        self.assertFalse(self.document["review_panel"]["human_reviewed"])
        self.assertFalse(self.document["review_panel"]["used_as_diagnostic_input"])
        self.assertEqual(self.document["provenance"]["provider_calls"],0)
        for case in self.document["cases"]:
            self.assertFalse(case["canonical"]["human_reviewed"])
            self.assertEqual(case["expected"]["semantic_identity_status"],"unknown")
            if case["scope"]=="adapter-only":
                self.assertFalse(case["semantic_service"]["semantic_quality_qualification"])
                self.assertEqual(case["semantic_service"]["real_provider_calls"],0)

    def test_no_output_cannot_satisfy_frozen_positive_and_negative_controls(self):
        for case in self.document["cases"]:
            self.assertFalse(score_case(case,{})["passed"],case["case_id"])

    def test_default_unknown_does_not_qualify_a_mock_that_was_never_called(self):
        record = {"identity_status":"unknown","semantic_adapter":{"kind":"mock-adapter-only","real_provider_calls":0,
                  "actual_local_mock_calls":0},"semantic":{"state":"insufficient_evidence","claims":[{"status":"unknown"}]}}
        result = score_case(self.case("service_low_evidence"),record)
        self.assertIn("semantic_mock_adapter_scope_only",result["failures"])

    def test_nested_upstream_report_and_failure_gate_preserve_exact_failure(self):
        case = self.case("upstream_geometry_fail")
        record = {"verification_status":"fail","upstream_preservation":{"all_reports_equal":True,"hashes_match":True,
                  "failure_gate_present":True},"report":{"findings":[]}}
        assertions = {a["name"]:a["passed"] for a in score_case(case,record)["assertions"]}
        self.assertTrue(assertions["same_upstream_geometry_fail_preserved"])
        self.assertTrue(assertions["overall_verification_cannot_pass"])
        record["upstream_preservation"]["hashes_match"] = False
        assertions = {a["name"]:a["passed"] for a in score_case(case,record)["assertions"]}
        self.assertFalse(assertions["same_upstream_geometry_fail_preserved"])

    def test_resolution_check_measures_changed_localization_not_only_authored_roi(self):
        from scripts.appearance_diagnostic_corpus.runner import resolution_observations
        region = {"region":{"view_id":"target","label":"colour_patch","bounds":[.2,.2,.4,.4]}}
        left = {"raster_resolution":32,"views":[{"regions":[region]}],
                "localization":[{"view_id":"target","changed_bounds_normalized":[.2,.2,.4,.4]}]}
        right = {"raster_resolution":64,"views":[{"regions":[region]}],
                 "localization":[{"view_id":"target","changed_bounds_normalized":[.6,.2,.8,.4]}]}
        check = resolution_observations(left,right)
        self.assertTrue(check["regions"][0]["bounds_within_tolerance"])
        self.assertFalse(check["matched_bounds_within_tolerance"])
        right["localization"][0]["changed_bounds_normalized"] = [.21,.21,.41,.41]
        self.assertTrue(resolution_observations(left,right)["matched_bounds_within_tolerance"])


if __name__=="__main__":
    unittest.main()
