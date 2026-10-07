"""Pinned shoulder-origin successor: preserve authority, never invent acceptance."""
import hashlib
import json
from pathlib import Path
import struct
import unittest

from core.modular_character import ModularCharacterSpec
from core.native_pose_probe import NativePoseProbe
from scripts.extract_stytch_pose_series import INDEX_SHA256, REVISION
from scripts.shoulder_pose_derivation import derive_pose, document
from scripts.workshop_doll_evidence import compare_reference, compare_shoulder_variant
from tests.test_authored_skin_doll_fixture import CANDIDATE_SHA as BASE_SHA, SOURCE_SHA as BASE_SOURCE_SHA, reader

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "example/v2/modular/StytchDollAuthoredSkin"
FIXTURE = BASE.parent / "StytchDollShoulderAligned"
CAPTURES = ROOT / "example/v2/poses/StytchDoll/complete"
GLB_SHA = "6654f85acb539e471ccc525f4ffc029409e96e98aeb524df1be95211e860d3f8"
SOURCE_SHA = "7d424323bfb70d7cd5abdd36af034ea30f30c210989f35677ef7b4049c71adbd"
GENERATOR_SHA = "5cd687e3536b0278224baedac827442b2000718f"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8"))


class ShoulderAlignedDollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.quality = read(FIXTURE / "manifest.json"), read(FIXTURE / "pose-quality.json")
        cls.old, cls.old_binary = reader.read_glb(BASE / "character.glb")
        cls.new, cls.new_binary = reader.read_glb(FIXTURE / "character.glb")

    def test_distinct_immutable_bundle_and_portable_authoring_provenance(self):
        self.assertEqual(digest(BASE / "character.glb"), BASE_SHA)
        self.assertEqual(digest(BASE / "source.blend"), BASE_SOURCE_SHA)
        self.assertEqual(digest(FIXTURE / "character.glb"), GLB_SHA)
        self.assertEqual(digest(FIXTURE / "source.blend"), SOURCE_SHA)
        self.assertEqual(self.manifest["sha256"], GLB_SHA)
        self.assertEqual(self.manifest["editable_source_sha256"], SOURCE_SHA)
        self.assertEqual(self.quality["source_sha"], GENERATOR_SHA)
        self.assertEqual(self.manifest["pose_quality_report_sha256"], digest(FIXTURE / "pose-quality.json"))
        for name, key in (("authoring.json", "authoring_sha256"),
                          ("partition-authoring.json", "partition_authoring_sha256")):
            self.assertEqual(read(FIXTURE / name), read(BASE / name))
            self.assertNotIn(b"\r", (FIXTURE / name).read_bytes())
            self.assertEqual(digest(FIXTURE / name), self.manifest[key])
        self.assertEqual((FIXTURE / "reference.glb").read_bytes(), (BASE / "reference.glb").read_bytes())
        self.assertEqual(self.manifest["source_authority_sha256"],
                         "0e7dc2647e9464508a25798aa087d30fe8e9c8fdabf1f650fb1961f818c7fae2")

    def test_only_declared_binds_change_without_weakening_other_gates(self):
        proof = compare_shoulder_variant(self.old, self.old_binary, self.new, self.new_binary, reader.read_accessor)
        self.assertEqual(proof, self.manifest["reference_fidelity"])
        self.assertTrue(proof["exact_surface_uv_skin_materials_atlas_preserved"])
        with self.assertRaisesRegex(ValueError, "inverse bind"):
            compare_reference(self.old, self.old_binary, self.new, self.new_binary, reader.read_accessor)
        changed = bytearray(self.new_binary)
        skin = self.new["skins"][0]
        index = [self.new["nodes"][n]["name"] for n in skin["joints"]].index("head")
        accessor = self.new["accessors"][skin["inverseBindMatrices"]]
        view = self.new["bufferViews"][accessor["bufferView"]]
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0) + index * view.get("byteStride", 64)
        struct.pack_into("<f", changed, offset + 48, struct.unpack_from("<f", changed, offset + 48)[0] + 1)
        with self.assertRaisesRegex(ValueError, "undeclared inverse bind"):
            compare_shoulder_variant(self.old, self.old_binary, self.new, bytes(changed), reader.read_accessor)
        changed = bytearray(self.new_binary)
        image = self.new["images"][0]
        changed[self.new["bufferViews"][image["bufferView"]].get("byteOffset", 0)] ^= 1
        with self.assertRaisesRegex(ValueError, "atlas"):
            compare_shoulder_variant(self.old, self.old_binary, self.new, bytes(changed), reader.read_accessor)

    def test_native_contract_and_strict_selected_source_fidelity(self):
        spec = self.new["asset"]["extras"]["meshvenn_modular_character"]["spec"]
        self.assertEqual(spec, self.old["asset"]["extras"]["meshvenn_modular_character"]["spec"])
        parsed = ModularCharacterSpec.from_dict(spec)
        self.assertEqual((len(parsed.regions), len(parsed.sockets)), (5, 8))
        self.assertEqual(len(self.new["skins"][0]["joints"]), 18)
        self.assertFalse(self.new.get("animations"))
        self.assertEqual(sum(self.manifest["regions"].values()), 7126)
        self.assertTrue(self.manifest["roundtrip"]["passed"])
        self.assertEqual(self.manifest["roundtrip"]["raw_normal_tolerance"], 2e-6)
        edit = self.manifest["shoulder_refinement"]
        self.assertEqual(edit["algorithm"], "authored-closed-shoulder-rings-v1")
        self.assertEqual(edit["changed_native_rest_origins"], ["upper_arm.L", "upper_arm.R"])
        self.assertTrue(edit["native_names_parents_and_axes_preserved"])
        self.assertLess(edit["unchanged_socket_parent_matrix_max_error"], 2e-4)

    def test_nineteen_derived_poses_preserve_exact_capture_lineage_and_gate_both_arms(self):
        index = read(CAPTURES / "index.json")
        self.assertEqual(digest(CAPTURES / "index.json"), INDEX_SHA256)
        self.assertEqual(self.quality["pose_set_sha256"], INDEX_SHA256)
        self.assertEqual(self.quality["consumer_pose_revision"], REVISION)
        self.assertEqual(self.quality["candidate_sha256"], GLB_SHA)
        self.assertEqual(self.quality["editable_source_sha256"], SOURCE_SHA)
        self.assertEqual(self.quality["baseline_sha256"], BASE_SHA)
        expected = {case["id"]: case for case in index["cases"]}
        self.assertEqual(self.quality["case_count"], 19)
        self.assertEqual(len(self.quality["cases"]), 19)
        self.assertEqual({case["id"] for case in self.quality["cases"]}, set(expected))
        for case in self.quality["cases"]:
            original = expected[case["id"]]
            for key in ("probe_sha256", "matrix_proof_sha256", "hidden_regions"):
                self.assertEqual(case[key], original[key])
            for name, key in ((original["probe"], "probe_sha256"), (original["matrix_proof"], "matrix_proof_sha256")):
                self.assertEqual(digest(CAPTURES / name), case[key])
            derived_path = FIXTURE / "derived-poses" / (case["id"] + ".json")
            self.assertEqual(digest(derived_path), case["derived_pose_sha256"])
            self.assertNotIn(b"\r", derived_path.read_bytes())
            derived = NativePoseProbe.from_dict(read(derived_path))
            old = NativePoseProbe.from_dict(read(CAPTURES / original["probe"]))
            recalculated = derive_pose(old, {bone.name: bone.rest for bone in derived.bones}, GLB_SHA)
            self.assertEqual(document(recalculated), document(derived))
            for role in ("left-arm", "right-arm"):
                before, after = case["baseline_cohorts"][role], case["candidate_cohorts"][role]
                self.assertEqual(after["edge_count"], before["edge_count"])
                self.assertLessEqual(after["p95_abs_log_length_ratio"], .8 * before["p95_abs_log_length_ratio"])
            if case["id"] in ("factory-hall", "factory-held"):
                for cohort in case["candidate_cohorts"].values():
                    self.assertEqual(cohort["collapsed_fraction"], 0)
            for key in ("source_vs_decoded_max_error_m", "decoded_vs_reimport_max_error_m",
                        "vertices_without_shoulder_influence_max_error_m"):
                self.assertLess(case[key], 2e-5 * 1.82)
            self.assertLess(case["rest_world_matrix_max_error"], 2e-6)
        self.assertTrue(self.quality["shoulder_metric_improves_every_pose"])
        self.assertTrue(self.quality["hall_held_collapsed_cohorts_eliminated"])

    def test_own_render_fingerprints_and_limits_cannot_claim_consumer_acceptance(self):
        self.assertEqual(len(self.quality["images"]), 14)
        for name, expected in self.quality["images"].items():
            self.assertEqual(Path(name).name, name)
            self.assertTrue(name.endswith(".png"))
            self.assertEqual(digest(FIXTURE / "poses" / name), expected)
        self.assertFalse(self.quality["visual_qualification"])
        self.assertFalse(self.quality["consumer_acceptance"])
        self.assertIn("NOT replayed", self.manifest["consumer_acceptance"])
        self.assertIn("not a new Stytch capture", self.quality["derivation"])
        self.assertTrue(self.manifest["remaining_limits"])


if __name__ == "__main__":
    unittest.main()
