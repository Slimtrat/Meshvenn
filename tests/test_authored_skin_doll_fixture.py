"""Distinct source-skin candidate: exact retained authority, honest pose evidence."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from core.modular_character import ModularCharacterSpec
from scripts.extract_stytch_pose_series import ASSET_SHA, INDEX_SHA256
from scripts.workshop_doll_evidence import compare_owned_variant, compare_reference

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "example/v2/modular/StytchDollAuthoredSkin"
BASELINE = ROOT / "example/v2/modular/StytchDoll"
READER_SPEC = importlib.util.spec_from_file_location("owned_fixture_reader", ROOT / "implementations/glb_export/modular_gltf.py")
reader = importlib.util.module_from_spec(READER_SPEC)
READER_SPEC.loader.exec_module(reader)
CANDIDATE_SHA = "dc0ba1f2129d09754f0ff53cf609a709338a6946acf1f8f341c8ae4624e4e9bc"
SOURCE_SHA = "69bb7e8af073c53703dd3e76cc6a1bce72fe7aea5b1628f8ea2d5e661243c724"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AuthoredSkinDollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURE / "manifest.json").read_text("utf-8"))
        cls.quality = json.loads((FIXTURE / "pose-quality.json").read_text("utf-8"))
        cls.old, cls.old_binary = reader.read_glb(BASELINE / "character.glb")
        cls.new, cls.new_binary = reader.read_glb(FIXTURE / "character.glb")

    def test_pinned_distinct_bundle_and_originals_survive(self):
        self.assertEqual(digest(BASELINE / "character.glb"), ASSET_SHA)
        self.assertEqual(digest(FIXTURE / "character.glb"), CANDIDATE_SHA)
        self.assertEqual(self.manifest["sha256"], CANDIDATE_SHA)
        self.assertNotEqual(CANDIDATE_SHA, ASSET_SHA)
        self.assertEqual(digest(FIXTURE / "source.blend"), SOURCE_SHA)
        self.assertEqual(self.manifest["editable_source_sha256"], SOURCE_SHA)
        for name in ("authoring.json", "partition-authoring.json", "reference.glb"):
            self.assertEqual((FIXTURE / name).read_bytes(), (BASELINE / name).read_bytes())
        self.assertEqual(self.manifest["pose_quality_report_sha256"], digest(FIXTURE / "pose-quality.json"))

    def test_exact_surface_material_bind_proof_does_not_weaken_old_weight_gate(self):
        proof = compare_owned_variant(self.old, self.old_binary, self.new, self.new_binary, reader.read_accessor)
        self.assertTrue(proof["passed"])
        self.assertEqual(proof["triangle_count"], 14252)
        self.assertGreater(proof["changed_corner_count"], 0)
        with self.assertRaises(ValueError):
            compare_reference(self.old, self.old_binary, self.new, self.new_binary, reader.read_accessor)
        changed = bytearray(self.new_binary)
        image = self.new["images"][0]
        changed[self.new["bufferViews"][image["bufferView"]].get("byteOffset", 0)] ^= 1
        with self.assertRaisesRegex(ValueError, "atlas"):
            compare_owned_variant(self.old, self.old_binary, self.new, bytes(changed), reader.read_accessor)

    def test_native_contract_and_new_source_fidelity_are_preserved(self):
        spec = self.new["asset"]["extras"]["meshvenn_modular_character"]["spec"]
        self.assertEqual(spec, self.old["asset"]["extras"]["meshvenn_modular_character"]["spec"])
        authoring = ModularCharacterSpec.from_dict(spec)
        self.assertEqual(len(authoring.regions), 5)
        self.assertEqual(len(authoring.sockets), 8)
        self.assertEqual(len(self.new["skins"][0]["joints"]), 18)
        self.assertFalse(self.new.get("animations"))
        counts = Counter(authoring.ownership["MeshvennScan"])
        self.assertEqual(sum(counts.values()), 7126)
        self.assertTrue(self.manifest["roundtrip"]["passed"])
        self.assertEqual(self.manifest["roundtrip"]["raw_normal_tolerance"], 2e-6)
        edit = self.manifest["body_refinement"]
        self.assertEqual(edit["algorithm"], "authored-regional-v1-axial-isolation")
        self.assertEqual(edit["changed_vertex_count"], 4193)
        self.assertEqual(edit["unchanged_distal_vertex_count"], 2935)
        self.assertEqual(edit["collar_in_heights"], .06)

    def test_all_nineteen_exact_poses_gate_metric_improvement_not_acceptance(self):
        quality = self.quality
        dataset = ROOT / "example/v2/poses/StytchDoll/complete"
        index = json.loads((dataset / "index.json").read_text("utf-8"))
        self.assertEqual(digest(dataset / "index.json"), INDEX_SHA256)
        self.assertEqual(quality["pose_set_sha256"], INDEX_SHA256)
        self.assertEqual(quality["captured_asset_sha256"], ASSET_SHA)
        self.assertEqual(quality["candidate"]["character.glb"], CANDIDATE_SHA)
        self.assertEqual(quality["candidate"]["source.blend"], SOURCE_SHA)
        self.assertEqual(quality["case_count"], 19)
        self.assertEqual(len(quality["cases"]), 19)
        self.assertEqual(quality["consumer_pose_revision"], index["source_revision"])
        self.assertRegex(quality["source_sha"], r"^[0-9a-f]{40}$")
        expected = {case["id"]: case for case in index["cases"]}
        self.assertEqual({case["id"] for case in quality["cases"]}, set(expected))
        for case in quality["cases"]:
            for key in ("probe_sha256", "matrix_proof_sha256", "hidden_regions"):
                self.assertEqual(case[key], expected[case["id"]][key])
            before, after = case["baseline_torso_edges"], case["candidate_torso_edges"]
            self.assertEqual(before["edge_count"], after["edge_count"])
            self.assertLessEqual(after["outside_20_percent_count"], .5*before["outside_20_percent_count"])
            self.assertLessEqual(after["p95_abs_log_length_ratio"], .7*before["p95_abs_log_length_ratio"])
            self.assertLess(case["source_vs_decoded_max_error_m"], 2e-5*1.82)
            self.assertLess(case["decoded_vs_reimport_max_error_m"], 2e-5*1.82)
        self.assertTrue(quality["torso_metric_improves_in_every_pose"])
        self.assertFalse(quality["visual_qualification"])
        self.assertFalse(quality["consumer_acceptance"])

    def test_own_blender_renders_are_fingerprinted_and_include_limits(self):
        self.assertEqual(len(self.quality["images"]), 14)
        for name, expected in self.quality["images"].items():
            self.assertEqual(Path(name).name, name)
            self.assertTrue(name.endswith(".png"))
            self.assertEqual(digest(FIXTURE / "poses" / name), expected)
        self.assertIn("NOT replayed", self.manifest["consumer_acceptance"])
        self.assertTrue(self.manifest["remaining_limits"])


if __name__ == "__main__":
    unittest.main()
