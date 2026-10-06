from __future__ import annotations

import copy
import json
import math
import unittest
from dataclasses import FrozenInstanceError

from core.modular_character import ModularCharacterSpec, mesh_surface_sha256


def fixture():
    return {
        "contract": "meshvenn.modular-character", "version": 1,
        "rig_id": "canonical-biped-v2", "rig_version": 2,
        "coordinates": {"units": "meters", "up_axis": "Y", "forward_axis": "+Z",
                        "handedness": "right", "normalization": {
                            "convention": "meshvenn-height-v1", "normalized_height": True,
                            "target_height": 2.0, "scale": 0.5}},
        "regions": [{"id": "core", "role": "body-core", "node_name": "Meshvenn_Core"},
                    {"id": "arm-left", "role": "left-arm", "node_name": "Meshvenn_LeftArm"}],
        "ownership": {"SourceMesh": ["core", "arm-left"]},
        "ownership_source_sha256": {"SourceMesh": "a" * 64},
        "seams": {"boundary_policy": "open-shared-vertices", "authoring_changes": [], "caps": []},
        "sockets": [{"id": "socket-left-arm", "role": "left-arm", "parent_bone": "hand.L",
                     "region_id": "arm-left", "translation": [0.1, 0.2, -0.3],
                     "rotation": [0.0, 0.0, 0.0, 1.0], "scale": [1.0, 1.0, 1.0],
                     "frame": "gltf-joint-local", "units": "meters"}],
    }


class ModularCharacterContractTests(unittest.TestCase):
    def spec(self):
        return ModularCharacterSpec.from_dict(fixture())

    def validate(self, spec=None, **updates):
        arguments = dict(mesh_face_counts={"SourceMesh": 2}, bone_names=("root", "hand.L"),
                         rig_id="canonical-biped-v2", rig_version=2,
                         mesh_surface_hashes={"SourceMesh": "a" * 64})
        arguments.update(updates)
        return (spec or self.spec()).validate_against(**arguments)

    def test_json_roundtrip_is_deterministic_and_declares_real_capabilities(self):
        spec = self.spec()
        data = spec.to_dict()
        self.assertEqual(ModularCharacterSpec.from_dict(json.loads(json.dumps(data))), spec)
        self.assertEqual(data["capabilities"], {"full_body_only": False, "modular_regions": True,
                         "supported_socket_ids": ["socket-left-arm"],
                         "supported_socket_roles": ["left-arm"], "missing_socket_roles": [],
                         "ambiguous_socket_roles": []})
        self.assertIs(self.validate(spec), spec)

    def test_declarations_and_buffers_are_immutable_and_not_aliased(self):
        source = fixture()
        spec = ModularCharacterSpec.from_dict(source)
        source["ownership"]["SourceMesh"][0] = "arm-left"
        source["sockets"][0]["translation"][0] = 42.0
        self.assertEqual(spec.ownership["SourceMesh"], ("core", "arm-left"))
        self.assertEqual(spec.sockets[0].translation, (0.1, 0.2, -0.3))
        with self.assertRaises(TypeError):
            spec.ownership["SourceMesh"] = ("core",)
        with self.assertRaises(FrozenInstanceError):
            spec.regions[0].role = "head"
        data = spec.to_dict()
        data["ownership"]["SourceMesh"][0] = "head"
        self.assertEqual(spec.ownership["SourceMesh"][0], "core")

    def test_single_body_region_honestly_declares_full_body_only(self):
        data = fixture()
        data["regions"] = data["regions"][:1]
        data["ownership"]["SourceMesh"] = ["core", "core"]
        data["sockets"] = []
        spec = ModularCharacterSpec.from_dict(data)
        self.assertTrue(spec.capabilities["full_body_only"])
        self.assertFalse(spec.capabilities["modular_regions"])
        self.assertEqual(spec.capabilities["supported_socket_roles"], [])

    def test_unknown_or_missing_fields_fail_at_every_level(self):
        for path in ((), ("coordinates",), ("coordinates", "normalization"),
                     ("seams",), ("regions", 0), ("sockets", 0)):
            for mutation in ("unknown", "missing"):
                with self.subTest(path=path, mutation=mutation):
                    data = fixture()
                    nested = data
                    for key in path:
                        nested = nested[key]
                    if mutation == "unknown":
                        nested["guessed"] = True
                    else:
                        nested.pop(next(iter(nested)))
                    with self.assertRaises((TypeError, ValueError)):
                        ModularCharacterSpec.from_dict(data)

    def test_unsupported_version_invalid_identifier_and_ambiguous_ids_fail(self):
        mutations = [lambda d: d.update(version=True), lambda d: d.update(version=2),
                     lambda d: d.update(rig_version="2"), lambda d: d.update(contract="other"),
                     lambda d: d["regions"][0].update(id="Core"),
                     lambda d: d["regions"][1].update(id="core"),
                     lambda d: d["regions"][1].update(role="body-core"),
                     lambda d: d["regions"][1].update(node_name="Meshvenn_Core"),
                     lambda d: d["sockets"][0].update(id="core"),
                     lambda d: d["sockets"].append(copy.deepcopy(d["sockets"][0]))]
        for mutate in mutations:
            data = fixture()
            mutate(data)
            with self.assertRaises((TypeError, ValueError)):
                ModularCharacterSpec.from_dict(data)

    def test_complete_unambiguous_ownership_and_region_references_are_required(self):
        mutations = [lambda d: d.update(ownership={}),
                     lambda d: d["ownership"].update(SourceMesh=[]),
                     lambda d: d["ownership"].update(SourceMesh=["core", "missing"]),
                     lambda d: d["ownership"].update(SourceMesh=["core", ["core", "arm-left"]]),
                     lambda d: d["ownership"].update(SourceMesh=["core", "core"]),
                     lambda d: d["sockets"][0].update(region_id="missing")]
        for mutate in mutations:
            data = fixture()
            mutate(data)
            with self.assertRaises((TypeError, ValueError)):
                ModularCharacterSpec.from_dict(data)
        data = fixture()
        data["ownership"]["OtherMesh"] = ["arm-left"]
        data["ownership_source_sha256"]["OtherMesh"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "multiple source"):
            ModularCharacterSpec.from_dict(data)

    def test_socket_trs_is_complete_finite_normalized_and_in_the_declared_frame(self):
        for values in ({"translation": [math.nan, 0, 0]}, {"translation": [0, 0]},
                       {"rotation": [0, 0, 0, 0]}, {"rotation": [0, 0, 0, 2]},
                       {"rotation": [0, 0, math.inf, 1]}, {"scale": [1, 0, 1]},
                       {"scale": [1, -1, 1]}, {"scale": [True, 1, 1]},
                       {"frame": "blender-bone-local"}, {"units": "centimeters"}):
            data = fixture()
            data["sockets"][0].update(values)
            with self.assertRaises((TypeError, ValueError)):
                ModularCharacterSpec.from_dict(data)

    def test_incompatible_coordinates_normalization_and_unsupported_caps_fail(self):
        for key, value in (("up_axis", "Z"), ("forward_axis", "-Y"), ("units", "centimeters"),
                           ("handedness", "left")):
            data = fixture()
            data["coordinates"][key] = value
            with self.assertRaises(ValueError):
                ModularCharacterSpec.from_dict(data)
        for values in ({"convention": "guess"}, {"scale": 0}, {"target_height": math.inf},
                       {"normalized_height": False}, {"normalized_height": 1}):
            data = fixture()
            data["coordinates"]["normalization"].update(values)
            with self.assertRaises((TypeError, ValueError)):
                ModularCharacterSpec.from_dict(data)
        for key in ("caps", "authoring_changes"):
            data = fixture()
            data["seams"][key] = [{"unvalidated": True}]
            with self.assertRaises(ValueError):
                ModularCharacterSpec.from_dict(data)

    def test_false_capabilities_cannot_publish_placeholder_or_ambiguous_sockets(self):
        data = self.spec().to_dict()
        data["capabilities"]["missing_socket_roles"] = ["head", "backpack"]
        spec = ModularCharacterSpec.from_dict(data)
        self.assertEqual(spec.missing_socket_roles, ("head", "backpack"))
        for key, value in (("modular_regions", 1), ("full_body_only", True),
                           ("supported_socket_roles", ["head"]),
                           ("ambiguous_socket_roles", ["left-arm"]),
                           ("missing_socket_roles", ["left-arm"])):
            wrong = self.spec().to_dict()
            wrong["capabilities"][key] = value
            with self.assertRaises((TypeError, ValueError)):
                ModularCharacterSpec.from_dict(wrong)
        wrong = fixture()
        wrong["capabilities"] = None
        with self.assertRaises(TypeError):
            ModularCharacterSpec.from_dict(wrong)

    def test_source_validation_rejects_missing_faces_bones_rig_and_stale_surface(self):
        for updates in ({"mesh_face_counts": {}}, {"mesh_face_counts": {"SourceMesh": 3}},
                        {"mesh_face_counts": {"SourceMesh": True}}, {"bone_names": ()},
                        {"bone_names": ("root",)}, {"bone_names": ("hand.L", "hand.L")},
                        {"rig_id": "canonical-biped-v1"}, {"rig_version": 1},
                        {"rig_version": True}, {"mesh_surface_hashes": {"SourceMesh": "b" * 64}},
                        {"mesh_surface_hashes": {}}, {"mesh_surface_hashes": {"SourceMesh": "A" * 64}}):
            with self.assertRaises((TypeError, ValueError)):
                self.validate(**updates)
        with self.assertRaises(TypeError):
            self.spec().validate_against({"SourceMesh": 2}, ("hand.L",), "canonical-biped-v2")

    def test_source_fingerprint_tracks_positions_topology_and_face_order(self):
        vertices = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
        polygons = [(0, 1, 2), (0, 2, 3)]
        value = mesh_surface_sha256(vertices, polygons)
        self.assertEqual(value, mesh_surface_sha256(vertices, polygons))
        self.assertNotEqual(value, mesh_surface_sha256(vertices, polygons[::-1]))
        moved = vertices.copy()
        moved[0] = (0, 0, 0.0001)
        self.assertNotEqual(value, mesh_surface_sha256(moved, polygons))
        self.assertEqual(value, mesh_surface_sha256([(-0.0, 0, 0), *vertices[1:]], polygons))
        for bad_vertices, bad_polygons in (([(math.nan, 0, 0), *vertices[1:]], polygons),
                                          (vertices, [(0, 0, 1)]), (vertices, [(0, 1, 9)])):
            with self.assertRaises((TypeError, ValueError)):
                mesh_surface_sha256(bad_vertices, bad_polygons)
