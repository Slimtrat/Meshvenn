"""Independent original data and frozen expectations; no D5 engine invocation."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.correction_plan_corpus.fixtures import build_corpus, mask_pixel
from scripts.correction_plan_corpus.integrity import load_manifest

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


if __name__ == "__main__":
    unittest.main()
