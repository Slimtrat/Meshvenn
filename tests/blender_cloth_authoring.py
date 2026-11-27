"""Numerical regressions for capture conventions and deformation-aware source LOD."""

from pathlib import Path
from copy import deepcopy
import json
import struct
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.cloth_lod import (
    protected_vertices,
    prune_weights,
    sampled_distance,
    transfer_weights,
)
from scripts.cloth_replay_math import accumulated, lbs, matrix, oriented, verify_frames
from scripts.qualify_cloth_modular import material_signature


def columns(value):
    return value[:3].T.reshape(-1).tolist()


class CaptureMathTests(unittest.TestCase):
    def test_basis_columns_and_complete_parent_local_pose(self):
        parent = np.array(
            ((0, -1, 0, 1), (1, 0, 0, 2), (0, 0, 1, 3), (0, 0, 0, 1)), float
        )
        local = np.identity(4)
        local[0, 3] = 2
        np.testing.assert_allclose(matrix(columns(parent)), parent)
        bones = [
            {"Index": 0, "Name": "root", "Parent": -1, "Pose": columns(parent)},
            {"Index": 1, "Name": "child", "Parent": 0, "Pose": columns(local)},
        ]
        pose = accumulated(bones, ["root", "child"], [-1, 0], "Pose")
        np.testing.assert_allclose(pose[1][:3, 3], (1, 4, 3))
        bones[1]["Parent"] = -1
        with self.assertRaises(ValueError):
            accumulated(bones, ["root", "child"], [-1, 0], "Pose")

    def test_rejects_ambiguous_or_invalid_matrices(self):
        for values in ([0] * 16, [True] * 12, [float("nan")] * 12, [0] * 12):
            with self.subTest(values=values), self.assertRaises(ValueError):
                matrix(values)
        reflected = np.diag((-1.0, 1, 1, 1))
        with self.assertRaises(ValueError):
            matrix(columns(reflected))

    def test_ancestor_facing_is_applied_exactly_once(self):
        identity = np.identity(4)
        facing = np.diag((-1.0, 1, -1, 1))
        ancestors = [
            {"Local": columns(identity), "World": columns(facing)},
            {"Local": columns(facing), "World": columns(facing)},
        ]
        frames = {
            "MeshAncestors": ancestors,
            "SkeletonAncestors": ancestors,
            "MeshWorld": columns(facing),
            "SkeletonWorld": columns(facing),
            "MeshToSkeleton": columns(identity),
        }
        np.testing.assert_allclose(verify_frames(frames), identity)
        frames["MeshToSkeleton"] = columns(facing)
        with self.assertRaises(ValueError):
            verify_frames(frames)

    def test_lbs_keeps_import_weight_quantization_visible(self):
        palette = np.array([np.identity(4), np.identity(4)])
        palette[1, 0, 3] = 2
        positions, normals = lbs(
            palette,
            np.array([[1.0, 0, 0]]),
            np.array([[0.0, 1, 0]]),
            np.array([[0, 1]]),
            np.array([[0.25, 0.5]]),
        )
        np.testing.assert_allclose(positions[0], (1.75, 0, 0))
        np.testing.assert_allclose(normals[0], (0, 1, 0))
        # Renormalizing .75 to 1 would conceal a real import/transport change.
        self.assertNotAlmostEqual(positions[0, 0], 1.75 / 0.75)

    def test_oriented_topology_does_not_accept_reversed_winding(self):
        self.assertEqual(oriented((1, 2, 3)), oriented((2, 3, 1)))
        self.assertNotEqual(oriented((1, 2, 3)), oriented((1, 3, 2)))


class SourceLodTests(unittest.TestCase):
    def test_material_gate_resolves_texture_identity_and_checks_normal_map(self):
        doc = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 8}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": 4},
                {"buffer": 0, "byteOffset": 4, "byteLength": 4},
            ],
            "images": [
                {"bufferView": 0, "mimeType": "image/png"},
                {"bufferView": 1, "mimeType": "image/png"},
            ],
            "samplers": [{"magFilter": 9729, "minFilter": 9987}],
            "textures": [{"source": 0, "sampler": 0}, {"source": 1, "sampler": 0}],
            "materials": [
                {
                    "normalTexture": {"index": 0},
                    "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}},
                }
            ],
        }

        def write(path, value):
            body = json.dumps(value).encode()
            body += b" " * (-len(body) % 4)
            binary = b"normbase"
            path.write_bytes(
                struct.pack("<4sII", b"glTF", 2, 28 + len(body) + len(binary))
                + struct.pack("<I4s", len(body), b"JSON")
                + body
                + struct.pack("<I4s", len(binary), b"BIN\0")
                + binary
            )

        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            first, second = Path(folder) / "first.glb", Path(folder) / "second.glb"
            write(first, doc)
            changed = deepcopy(doc)
            changed["textures"].reverse()
            changed["materials"][0]["normalTexture"]["index"] = 1
            changed["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"][
                "index"
            ] = 0
            changed["materials"][0]["extras"] = {"producer_note": "new provenance"}
            write(second, changed)
            self.assertEqual(material_signature(first), material_signature(second))
            changed["materials"][0]["normalTexture"]["index"] = 0
            write(second, changed)
            self.assertNotEqual(material_signature(first), material_signature(second))

    def test_skin_transfer_uses_source_surface_not_nearest_vertex(self):
        surface = ([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
        result = transfer_weights(
            surface, [{"a": 1}, {"b": 1}, {"c": 1}], [(0.2, 0.3, 0.01)]
        )
        for name, expected in (("a", 0.5), ("b", 0.2), ("c", 0.3)):
            self.assertAlmostEqual(result[0][name], expected, places=6)

    def test_pruning_measures_lost_mass_before_normalizing(self):
        result, loss = prune_weights(
            [{"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.08, "e": 0.02}]
        )
        self.assertAlmostEqual(loss, 0.02)
        self.assertEqual(len(result[0]), 4)
        self.assertAlmostEqual(sum(result[0].values()), 1)
        with self.assertRaises(ValueError):
            prune_weights([{}])
        portable, tiny_loss = prune_weights(
            [{"a": 0.99983, "b": 0.00008, "c": 0.00009}]
        )
        self.assertEqual(portable, [{"a": 1.0}])
        self.assertAlmostEqual(tiny_loss, 0.00017)

    def test_gradient_and_feedback_protect_a_single_neighbor_ring(self):
        edges = [(0, 1), (1, 2), (2, 3), (3, 4)]
        weights = [
            {"a": 1},
            {"a": 1},
            {"a": 0.5, "b": 0.5},
            {"a": 0.5, "b": 0.5},
            {"a": 0.5, "b": 0.5},
        ]
        self.assertEqual(protected_vertices(edges, weights, 0.005, 0.06), {0, 1, 2, 3})
        uniform = [{"a": 1}] * 5
        self.assertEqual(
            protected_vertices(edges, uniform, 0.005, 0.06, extra=[2]), {1, 2, 3}
        )

    def test_bidirectional_surface_error_and_feedback(self):
        original = ([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
        shifted = ([(0, 0, 1), (1, 0, 1), (0, 1, 1)], [(0, 1, 2)])
        distance = sampled_distance(original, shifted, protect_above=0.5)
        self.assertAlmostEqual(distance["max"], 1)
        self.assertEqual(distance["samples"], 8)
        self.assertEqual(distance["feedback_source_vertices"], [0, 1, 2])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
