"""Independent original data and frozen expectations; no D5 engine invocation."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.correction_plan_corpus.fixtures import build_corpus, mask_pixel
from scripts.correction_plan_corpus.integrity import load_manifest
from scripts.correction_plan_corpus.scoring import score_case
from scripts.correction_plan_corpus.sources import NativeLibraryRequired, execute_source

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT/"tests/fixtures/diagnostics/correction-plan-v1"


class CorrectionCorpusFreezeTests(unittest.TestCase):
    def test_original_manifest_and_assets_are_frozen(self):
        manifest,digest = load_manifest(CORPUS)
        self.assertEqual(18,len(manifest["cases"]))
        self.assertTrue(manifest["expectations_frozen_before_D5_evaluation"])
        with tempfile.TemporaryDirectory() as folder:
            recreated,other = build_corpus(Path(folder))
            self.assertEqual(digest,other)
            self.assertEqual(manifest,recreated)

    def test_original_shape_is_asymmetric_and_shift_does_not_clip(self):
        shape = {(x,y) for y in range(64) for x in range(64) if mask_pixel(x,y)}
        self.assertNotEqual(shape,{(63-x,y) for x,y in shape})
        shifted = {(x+5,y-3) for x,y in shape}
        self.assertEqual(len(shape),len(shifted))
        self.assertTrue(all(0<x<63 and 0<y<63 for x,y in shifted))

    def test_frozen_labels_cannot_be_relaxed(self):
        document = json.loads((CORPUS/"manifest.json").read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            document["cases"][0]["expected"]["controls"] = []
            root = Path(folder)
            (root/"manifest.json").write_text(json.dumps(document),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"Frozen correction manifest changed"):
                load_manifest(root)

    def test_capability_limits_and_stale_dependencies_are_explicit(self):
        document,_ = load_manifest(CORPUS)
        cases = {c["case_id"]:c for c in document["cases"]}
        self.assertFalse(cases["unsupported_masks"]["capabilities"]["masks"])
        self.assertEqual(1,cases["unsupported_multiple_references"]["capabilities"]["max_references"])
        self.assertFalse(cases["unsupported_camera_control"]["capabilities"]["camera_constraints"])
        self.assertEqual({"source","capabilities","report","policy"},
                         {c["prepare_mutation"]["kind"] for c in cases.values() if c["prepare_mutation"]})

    def test_no_human_provider_or_real_photo_qualification_is_invented(self):
        document,_ = load_manifest(CORPUS)
        self.assertFalse(document["provenance"]["human_reviewed"])
        self.assertFalse(document["provenance"]["provider_fidelity_qualified"])
        self.assertEqual(0,document["provenance"]["real_provider_calls"])
        user = next(c for c in document["cases"] if c["case_id"]=="user_original_preserved")
        self.assertIn("Analytic stand-in",user["author_intent"]["provenance_limit"])

    def test_no_output_cannot_satisfy_any_case(self):
        manifest,_ = load_manifest(CORPUS)
        for case in manifest["cases"]:
            self.assertFalse(score_case(case,{})["passed"],case["case_id"])

    def test_real_D2_preparation_evidence_is_not_a_handmade_report(self):
        manifest,_ = load_manifest(CORPUS)
        cases = {c["case_id"]:c for c in manifest["cases"]}
        shifted = execute_source(CORPUS,cases["framing_preparation"])
        self.assertEqual(1,len(shifted["upstream_result"].proposals))
        bad_mask = execute_source(CORPUS,cases["mask_preparation"])
        self.assertTrue(any(f.code=="input.empty_mask" and f.status=="fail" for f in bad_mask["reports"][0].findings))

    def test_real_D4_measures_the_original_authored_target_region(self):
        manifest,_ = load_manifest(CORPUS)
        case = next(c for c in manifest["cases"] if c["case_id"]=="targeted_visible_colour")
        context = execute_source(CORPUS,case)
        region = context["annotation"]["region"]
        measured = [r for v in context["upstream_result"].views for r in v.regions if r.region==region]
        self.assertTrue(measured)
        self.assertTrue(all(r.color_status=="fail" and r.changed_samples>0 and r.coverage_status=="pass" for r in measured))
        self.assertGreater(context["annotation"]["mask"].occupied_count,0)
        self.assertEqual("unknown",context["upstream_result"].identity_status)

    def test_low_confidence_mock_is_called_but_does_not_qualify_identity(self):
        manifest,_ = load_manifest(CORPUS)
        case = next(c for c in manifest["cases"] if c["case_id"]=="low_support_semantic_claim")
        context = execute_source(CORPUS,case)
        self.assertEqual(1,context["semantic_mock_calls"])
        self.assertEqual("unknown",context["upstream_result"].identity_status)
        claims = context["upstream_result"].semantic.claims
        self.assertTrue(claims)
        self.assertTrue(all(c.status=="unknown" for c in claims))
        self.assertTrue(all(raw.confidence==.2 and raw.support=="limited" for c in claims for raw in c.claims))

    def test_missing_native_library_never_substitutes_fake_geometry(self):
        manifest,_ = load_manifest(CORPUS)
        case = next(c for c in manifest["cases"] if c["case_id"]=="ambiguous_geometry")
        with self.assertRaises(NativeLibraryRequired):
            execute_source(CORPUS,case)

    def test_partial_engine_diagnosis_cannot_authorize_an_edit(self):
        manifest,_ = load_manifest(CORPUS)
        case = next(c for c in manifest["cases"] if c["case_id"]=="native_engine_failure")
        record = {"result":{"completion":"partial","verification_status":"unknown","plans":[]}}
        self.assertNotIn("planning_incomplete",score_case(case,record)["failures"])
        self.assertFalse(score_case(case,record)["passed"])
        record["result"]["plans"] = [{"action_kind":"edit_region","readiness":"ready"}]
        self.assertIn("planning_incomplete",score_case(case,record)["failures"])


if __name__ == "__main__":
    unittest.main()
