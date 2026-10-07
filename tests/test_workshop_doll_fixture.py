"""Pin the actual Stytch doll, not a substitute UAL1 or an appearance claim."""
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from core.modular_character import ModularCharacterSpec
from scripts.workshop_doll_evidence import compare_reference

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "example/v2/modular/StytchDoll"
READER_SPEC = importlib.util.spec_from_file_location(
    "workshop_fixture_reader", ROOT / "implementations/glb_export/modular_gltf.py")
reader = importlib.util.module_from_spec(READER_SPEC)
READER_SPEC.loader.exec_module(reader)
REFERENCE_SHA = "169ec90b326ccb71c1868dc26e7676e80a53990e9906a6ab4d23af04118d2034"
SURFACE_SHA = "4f18119c54fe408c8c6ca8859c5f7f56bf96a77b57d36ffb472ad6e83fb307ad"
COUNTS = {"body-core": 3400, "left-arm": 674, "right-arm": 674,
          "left-leg": 1168, "right-leg": 1210}


class WorkshopDollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURE / "manifest.json").read_text("utf-8"))
        cls.authoring = json.loads((FIXTURE / "authoring.json").read_text("utf-8"))
        cls.plan = json.loads((FIXTURE / "partition-authoring.json").read_text("utf-8"))
        cls.document, cls.binary = reader.read_glb(FIXTURE / "character.glb")
        cls.reference, cls.reference_binary = reader.read_glb(FIXTURE / "reference.glb")

    def compare(self, document=None, binary=None, decode=reader.read_accessor):
        return compare_reference(self.reference, self.reference_binary,
                                 self.document if document is None else document,
                                 self.binary if binary is None else binary, decode)

    def test_public_bundle_hashes_and_pinned_origin(self):
        for name, expected in (("character.glb", self.manifest["sha256"]),
                               ("source.blend", self.manifest["editable_source_sha256"]),
                               ("reference.glb", REFERENCE_SHA)):
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), expected)
        origin = self.manifest["source_provenance"]
        self.assertEqual(origin["revision"], "47cd554510c6229fe01a8b56cb16660f846a1ed2")
        self.assertEqual(origin["meshvenn_generation_revision"], "541986da530c28543f342b50a23fac3dfb771fbc")
        self.assertIn("explicitly authorized", origin["publication"])
        self.assertNotIn("CC0", json.dumps(origin))
        for name in ("authoring.json", "partition-authoring.json", "manifest.json"):
            self.assertNotIn("?token=", (FIXTURE / name).read_text("utf-8"))

    def test_frozen_face_selections_cover_exact_native_source(self):
        spec = ModularCharacterSpec.from_dict(self.authoring)
        self.assertEqual(dict(Counter(spec.ownership["MeshvennScan"])), COUNTS)
        self.assertEqual(dict(spec.ownership_source_sha256), {"MeshvennScan": SURFACE_SHA})
        self.assertEqual(self.plan["source_surface_sha256"], SURFACE_SHA)
        self.assertFalse(self.plan["design"]["weights_used_to_classify"])
        self.assertFalse(self.plan["design"]["ual1_planes_reused"])
        owners = ["body-core"] * 7126
        used = set()
        for role, declaration in self.plan["selections"].items():
            for index in declaration["polygon_indices"]:
                self.assertNotIn(index, used)
                used.add(index)
                owners[index] = role
        self.assertEqual(tuple(owners), spec.ownership["MeshvennScan"])
        self.assertEqual(self.manifest["regions"], COUNTS)
        self.assertEqual(self.manifest["triangle_count"], 14252)
        self.assertLessEqual(self.manifest["triangle_count"], 18000)

    def test_only_five_surface_nodes_one_native_skin_no_clips(self):
        envelope = self.document["asset"]["extras"]["meshvenn_modular_character"]
        self.assertEqual(envelope, self.manifest["contract"])
        self.assertEqual(envelope["spec"], self.authoring)
        bindings = envelope["bindings"]
        meshes = [(index, node) for index, node in enumerate(self.document["nodes"]) if "mesh" in node]
        self.assertEqual({index for index, _ in meshes}, set(bindings["region_nodes"].values()))
        self.assertEqual(len(meshes), 5)
        self.assertEqual(len(self.document["meshes"]), 5)
        self.assertEqual(len(self.document["skins"]), 1)
        self.assertEqual(len(self.document["skins"][0]["joints"]), 18)
        self.assertTrue(all(node["skin"] == bindings["skin"] for _, node in meshes))
        self.assertFalse(self.document.get("animations"))
        self.assertEqual(self.manifest["animation_count"], 0)

    def test_eight_native_joint_local_sockets_keep_source_scale(self):
        spec = ModularCharacterSpec.from_dict(self.authoring)
        expected = {"head": ("head", "body-core"), "left-arm": ("hand.L", "left-arm"),
                    "right-arm": ("hand.R", "right-arm"), "left-leg": ("foot.L", "left-leg"),
                    "right-leg": ("foot.R", "right-leg"), "back": ("chest", "body-core"),
                    "backpack": ("spine", "body-core"), "wing": ("chest", "body-core")}
        self.assertEqual({s.role: (s.parent_bone, s.region_id) for s in spec.sockets}, expected)
        self.assertEqual({s.id for s in spec.sockets}, {"attach-" + role for role in expected})
        for socket in spec.sockets:
            self.assertTrue(any(socket.translation))
            self.assertAlmostEqual(sum(value * value for value in socket.rotation), 1, places=6)
            self.assertTrue(all(abs(value - 1) < 1e-5 for value in socket.scale))
        self.assertEqual(len(self.manifest["socket_authoring"]), 8)

    def test_decoded_reference_proof_and_unchanged_strict_source_gates(self):
        evidence = self.compare()
        self.assertEqual(evidence, self.manifest["reference_fidelity"])
        self.assertEqual(evidence["max_weight_error"], 0)
        self.assertEqual(evidence["max_inverse_bind_error"], 0)
        self.assertEqual(evidence["corner_count"], 42756)
        proof = self.manifest["roundtrip"]
        self.assertTrue(proof["passed"])
        self.assertEqual(proof["raw_normal_tolerance"], 2e-6)
        self.assertEqual(proof["max_raw_normal_error"], 0)
        self.assertEqual(proof["max_hide_independence_error"], 0)
        self.assertTrue(self.manifest["source_authority_unchanged"])
        self.assertTrue(self.manifest["no_rebuild_verified"])
        self.assertEqual(len(self.manifest["source_authority_sha256"]), 64)

    def test_original_appearance_limits_are_not_relabelled_as_success(self):
        appearance = self.manifest["appearance"]
        self.assertFalse(appearance["regenerated"])
        self.assertFalse(appearance["full_appearance_qualified"])
        self.assertEqual(appearance["input_view_count"], 2)
        self.assertEqual(appearance["surface_samples"], 607569)
        self.assertEqual(appearance["neutral_fallback_samples"], 340385)
        self.assertAlmostEqual(appearance["neutral_fallback_ratio"], 340385 / 607569)
        self.assertEqual(appearance["uv_overlap_pixels"], 1)
        self.assertIn("downstream", self.manifest["consumer_acceptance"])

    def test_committed_renders_hash_the_final_glb_without_a_ci_claim(self):
        folder = FIXTURE / "previews"
        proof = json.loads((folder / "preview.json").read_text("utf-8"))
        self.assertEqual(proof["artifact_sha256"], self.manifest["sha256"])
        self.assertEqual(proof["reference_sha256"], REFERENCE_SHA)
        self.assertEqual(proof["source_sha"], "local-uncommitted")
        self.assertIsNone(proof["run_id"])
        self.assertIsNone(proof["run_attempt"])
        self.assertIn("NOT an imported animation", proof["pose_kind"])
        self.assertTrue(proof["rendered_from_final_glb"])
        self.assertEqual(set(proof["images"]), {"source.png", "rest.png", "compound.png",
            "hidden_left_arm.png", "sockets_rest.png", "sockets_compound.png"})
        for name, expected in proof["images"].items():
            self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), expected)

    def mutated_decode(self, accessor, transform):
        def decode(document, binary, index):
            values = reader.read_accessor(document, binary, index)
            if document is self.document and index == accessor:
                values = list(values)
                values[0] = transform(tuple(values[0]))
            return values
        return decode

    def test_corner_uv_mutation_is_rejected(self):
        index = self.document["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"]
        with self.assertRaises(ValueError):
            self.compare(decode=self.mutated_decode(index, lambda v: (v[0] + .01, v[1])))

    def test_reversed_winding_is_rejected(self):
        index = self.document["meshes"][0]["primitives"][0]["indices"]
        def decode(document, binary, current):
            values = list(reader.read_accessor(document, binary, current))
            if document is self.document and current == index:
                values[0], values[1] = values[1], values[0]
            return values
        with self.assertRaises(ValueError):
            self.compare(decode=decode)

    def test_skin_weight_mutation_is_rejected(self):
        index = self.document["meshes"][0]["primitives"][0]["attributes"]["WEIGHTS_0"]
        with self.assertRaises(ValueError):
            self.compare(decode=self.mutated_decode(index, lambda v: (v[0] + .01, *v[1:])))

    def test_inverse_bind_mutation_is_rejected(self):
        index = self.document["skins"][0]["inverseBindMatrices"]
        with self.assertRaises(ValueError):
            self.compare(decode=self.mutated_decode(index, lambda v: (v[0] + .01, *v[1:])))

    def test_baked_image_byte_mutation_is_rejected(self):
        binary = bytearray(self.binary)
        view = self.document["bufferViews"][self.document["images"][0]["bufferView"]]
        binary[view.get("byteOffset", 0)] ^= 1
        with self.assertRaises(ValueError):
            self.compare(binary=binary)

    def test_extra_unskinned_surface_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["nodes"].append({"mesh": 0})
        with self.assertRaises(ValueError):
            self.compare(document=document)

    def test_old_reference_normals_are_explicitly_diagnostic_not_source_gate(self):
        index = self.document["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]
        proof = self.compare(decode=self.mutated_decode(index, lambda v: (v[0] + .01, *v[1:])))
        self.assertGreater(proof["reference_glb_normal_delta"], .005)
        self.assertIn("Diagnostic", proof["normal_scope"])
        self.assertIn("separately gated", proof["normal_scope"])


if __name__ == "__main__":
    unittest.main()
