"""Distinct intentional skin edit must not launder old-source visual acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts.workshop_doll_evidence import compare_head_variant, compare_reference
from tests.test_workshop_doll_fixture import FIXTURE as BASELINE, reader

FIXTURE = BASELINE.parent / "StytchDollHeadIsolated"


class HeadIsolatedFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURE / "manifest.json").read_text("utf-8"))
        cls.document, cls.binary = reader.read_glb(FIXTURE / "character.glb")
        cls.reference, cls.reference_binary = reader.read_glb(BASELINE / "reference.glb")

    def compare(self, document=None, binary=None):
        return compare_head_variant(self.reference, self.reference_binary,
                                    self.document if document is None else document,
                                    self.binary if binary is None else binary, reader.read_accessor,
                                    self.manifest["glb_accessor_head_envelope"])

    def test_distinct_fingerprints_and_retained_accepted_baseline(self):
        baseline = json.loads((BASELINE / "manifest.json").read_text("utf-8"))
        self.assertEqual(baseline["sha256"], "76590fd9c335335255f2eb2a4fc0866adf3c5a6a6fad0d4938c9e7550b7dcb57")
        self.assertNotEqual(self.manifest["sha256"], baseline["sha256"])
        self.assertEqual(self.manifest["baseline_artifact_sha256"], baseline["sha256"])
        for name, expected in (("character.glb", self.manifest["sha256"]),
                               ("source.blend", self.manifest["editable_source_sha256"])):
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), expected)
        for name in ("reference.glb", "authoring.json", "partition-authoring.json"):
            self.assertEqual((FIXTURE / name).read_bytes(), (BASELINE / name).read_bytes())
        self.assertEqual(self.manifest["contract"], baseline["contract"])
        self.assertEqual(self.manifest["appearance"], baseline["appearance"])
        self.assertFalse(self.manifest["source_authority_unchanged"])
        self.assertTrue(self.manifest["selected_refined_source_unchanged_during_export"])
        self.assertIn("NOT been replayed", self.manifest["consumer_acceptance"])

    def test_selected_new_weights_pass_without_weakening_old_weight_gate(self):
        proof = self.compare()
        self.assertTrue(proof["passed"] and proof["intentional_head_weights_edit"])
        self.assertTrue(proof["below_neck_weights_exact"])
        self.assertGreater(proof["changed_corner_count"], 1000)
        with self.assertRaises(ValueError):
            compare_reference(self.reference, self.reference_binary, self.document, self.binary, reader.read_accessor)

    def test_unchanged_skin_geometry_or_atlas_cannot_masquerade_as_refinement(self):
        with self.assertRaises(ValueError):
            compare_head_variant(self.reference, self.reference_binary, self.reference, self.reference_binary,
                                 reader.read_accessor, self.manifest["glb_accessor_head_envelope"])
        damaged = bytearray(self.binary)
        view = self.document["bufferViews"][self.document["images"][0]["bufferView"]]
        damaged[view.get("byteOffset", 0)+50] ^= 1
        with self.assertRaises(ValueError):
            self.compare(binary=bytes(damaged))
        changed = copy.deepcopy(self.document)
        changed["materials"][0]["pbrMetallicRoughness"]["roughnessFactor"] = .25
        with self.assertRaises(ValueError):
            self.compare(document=changed)

    def test_raw_no_rebuild_gates_and_limits_are_not_relaxed(self):
        raw = self.manifest["roundtrip"]
        self.assertTrue(raw["passed"])
        self.assertEqual(raw["raw_normal_tolerance"], 2e-6)
        self.assertLessEqual(raw["max_raw_normal_error"], 2e-6)
        self.assertEqual(self.manifest["native_joint_count"], 18)
        self.assertEqual(self.manifest["animation_count"], 0)
        self.assertEqual(self.manifest["head_refinement"]["changed_vertex_count"], 2150)
        self.assertFalse(self.manifest["appearance"]["full_appearance_qualified"])

    def test_seven_actual_glb_probes_and_images_have_exact_provenance(self):
        quality = json.loads((FIXTURE / "quality/quality.json").read_text("utf-8"))
        self.assertTrue(quality["passed"] and quality["rendered_from_final_glb"])
        self.assertFalse(quality["neck_quality_qualified"])
        self.assertFalse(quality["full_appearance_qualified"])
        self.assertEqual(quality["candidate"]["artifact_sha256"], self.manifest["sha256"])
        self.assertEqual(quality["baseline"]["artifact_sha256"], self.manifest["baseline_artifact_sha256"])
        self.assertEqual(len(quality["candidate"]["poses"]), 7)
        self.assertEqual({p["id"] for p in quality["candidate"]["poses"]}, set(quality["rotations"]))
        self.assertEqual(len(quality["images"]), 6)
        for name, expected in quality["images"].items():
            self.assertEqual(hashlib.sha256((FIXTURE / "quality" / name).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
