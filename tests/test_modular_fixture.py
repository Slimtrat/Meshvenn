"""Pin the actual editable/generated fixture, separate from consumer acceptance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from core.modular_character import ModularCharacterSpec


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "example/v2/modular/UAL1"
SPEC = importlib.util.spec_from_file_location(
    "fixture_glb_reader", ROOT / "implementations/glb_export/modular_gltf.py")
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


class ModularFixtureTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((FIXTURE / "manifest.json").read_text("utf-8"))
        self.authoring = json.loads((FIXTURE / "authoring.json").read_text("utf-8"))
        self.document, self.binary = reader.read_glb(FIXTURE / "character.glb")

    def test_artifact_and_editable_source_are_hash_linked(self):
        for filename, key in (("character.glb", "sha256"), ("source.blend", "editable_source_sha256")):
            payload = (FIXTURE / filename).read_bytes()
            self.assertGreater(len(payload), 1024)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), self.manifest[key])
        self.assertEqual(self.manifest["native_joint_count"], 18)
        self.assertEqual(self.manifest["source_connectivity"]["component_count"], 1)
        self.assertEqual(self.manifest["animation_count"], 43)
        self.assertEqual(self.manifest["source_asset"], "quaternius_ual1")
        self.assertEqual(self.manifest["source_license"], "CC0-1.0")
        self.assertIn("uv-bake-v2", self.manifest["pipeline"])
        source = ROOT / "example/v2/assets/UAL1_Standard.glb"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), self.manifest["source_sha256"])

    def test_contract_binds_five_regions_to_one_native_skin(self):
        spec = ModularCharacterSpec.from_dict(self.authoring)
        self.assertEqual(spec.rig_id, "canonical-biped-v2")
        self.assertEqual(spec.rig_version, 2)
        self.assertEqual({region.role for region in spec.regions},
                         {"body-core", "left-arm", "right-arm", "left-leg", "right-leg"})
        envelope = self.document["asset"]["extras"]["meshvenn_modular_character"]
        self.assertEqual(envelope, self.manifest["contract"])
        self.assertEqual(envelope["spec"], self.authoring)
        bindings = envelope["bindings"]
        self.assertEqual(len(self.document["skins"]), 1)
        self.assertEqual(len(self.document["skins"][0]["joints"]), 18)
        self.assertEqual(len(bindings["joint_nodes"]), 18)
        for region in spec.regions:
            node = self.document["nodes"][bindings["region_nodes"][region.id]]
            self.assertEqual(node["name"], region.node_name)
            self.assertEqual(node["skin"], bindings["skin"])
            self.assertEqual(node["extras"]["meshvenn_region_id"], region.id)
        self.assertEqual(len(self.document["animations"]), 43)
        self.assertTrue(all("uri" not in image for image in self.document.get("images", [])))

    def test_surface_and_socket_evidence_is_explicit(self):
        finish = self.manifest["surface_refinement"]
        self.assertEqual(finish["micro_finish"]["algorithm"], "bounded-laplacian-v1")
        self.assertEqual(finish["micro_finish"]["iterations"], 6)
        self.assertTrue(finish["face_orientation_preserved"])
        self.assertLessEqual(finish["maximum_displacement_in_voxels"], .75)
        spec = ModularCharacterSpec.from_dict(self.authoring)
        self.assertEqual(len(spec.sockets), 8)
        self.assertEqual({socket.role for socket in spec.sockets},
                         {"head", "left-arm", "right-arm", "left-leg", "right-leg", "back", "wing", "backpack"})
        self.assertTrue(all(any(socket.translation) for socket in spec.sockets))
        coverage = self.manifest["partition_authoring"]["surface_coverage"]
        self.assertEqual(sum(coverage["region_polygon_counts"].values()), coverage["source_polygon_count"])
        self.assertEqual(coverage["source_polygon_count"], sum(len(values) for values in spec.ownership.values()))
        self.assertEqual(coverage["unowned_source_polygons"], 0)
        self.assertEqual(coverage["duplicated_source_polygons"], 0)
        self.assertEqual(coverage["extra_cap_polygons"], 0)
        self.assertGreater(coverage["new_inter_region_seam_edges"], 0)
        self.assertTrue(self.manifest["roundtrip"]["passed"])
        self.assertIn("separate", self.manifest["consumer_acceptance"])

    def test_appearance_is_real_color_separate_from_neutral_geometry(self):
        self.assertEqual(self.manifest["geometry_input_mode"], "neutral-silhouette")
        self.assertEqual(self.manifest["material_input_mode"], "source-color-projection")
        proof = self.manifest["appearance"]
        self.assertTrue(proof["passed"])
        self.assertEqual(proof["source_sha256"], self.manifest["source_sha256"])
        self.assertEqual(proof["render_mode"], "base-color-emission")
        self.assertFalse(proof["lighting_baked"])
        self.assertEqual(proof["texture_size"], 512)
        self.assertEqual(proof["samples_per_axis"], 2)
        self.assertEqual(proof["atlas_storage"], "srgb-byte-from-scene-linear")
        self.assertEqual(len(proof["views"]), 10)
        self.assertTrue(all(record["alpha_occupied_pixels"] > 0 for record in proof["views"]))
        self.assertLess(proof["neutral_fallback_ratio"], .01)
        self.assertGreater(proof["atlas_signal"]["chromatic_fraction"], .90)
        self.assertLess(proof["atlas_signal"]["white_fraction"], .01)
        transport = proof["color_transport"]
        self.assertTrue(transport["passed"])
        self.assertLessEqual(transport["max_linear_error"], .004)
        self.assertEqual(transport["source_linear_rgb"], [.25, .5, .75])
        self.assertIn("not general", proof["scope"])


if __name__ == "__main__":
    unittest.main()
