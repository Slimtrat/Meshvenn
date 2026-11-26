"""Real reconstruction provenance, with optional completed Blender artifact checks.

Set MESHVENN_CHARACTER_QUALITY_OUTPUT to the NEW directory produced by
scripts/character_quality/reconstruct.py to validate the real native/GLB run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.character_quality import reconstruct
from scripts.character_quality.blender_scene import png_mask


class ReconstructionContractTests(unittest.TestCase):
    def test_import_outside_blender_does_not_load_bpy(self):
        code = (
            "import sys;sys.path.insert(0," + repr(str(ROOT)) + ");"
            "from scripts.character_quality.reconstruct import reconstruct_cases;"
            "assert 'bpy' not in sys.modules"
        )
        subprocess.run([sys.executable, "-I", "-c", code], check=True, timeout=20)

    def test_invalid_configuration_never_creates_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-created"
            invalid = (
                {"resolution": True}, {"resolution": 129},
                {"mask_size": 0}, {"hero_size": 1025},
                {"view_counts": (2, 2)}, {"view_counts": (True,)},
                {"view_counts": ()}, {"view_counts": (3,)},
            )
            for values in invalid:
                with self.subTest(values=values), self.assertRaises(ValueError):
                    reconstruct.reconstruct_cases(output, "missing-library", **values)
                self.assertFalse(output.exists())

    def test_view_counts_and_poles_have_declared_physical_sides(self):
        from core.projection_frame import native_projection_axes
        views = [dict(id=name) for name, _, _ in reconstruct.ANGLES]
        self.assertEqual([v["id"] for v in reconstruct._selected(2, views)], ["az000", "az090"])
        self.assertEqual(len(reconstruct._selected(8, views)), 8)
        self.assertEqual(len(reconstruct._selected(10, views)), 10)
        poles = {name: native_projection_axes(a, e)[2] for name, a, e in reconstruct.ANGLES[-2:]}
        self.assertGreater(poles["top"][2], .999999)
        self.assertLess(poles["bottom"][2], -.999999)

    def test_mask_png_keeps_bottom_left_sample_convention(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            png_mask(path, 2, bytes((1, 0, 0, 1)))
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            position = 8
            compressed = b""
            while position < len(data):
                length = struct.unpack_from(">I", data, position)[0]
                kind = data[position + 4:position + 8]
                payload = data[position + 8:position + 8 + length]
                if kind == b"IDAT":
                    compressed += payload
                position += length + 12
            rows = zlib.decompress(compressed)
            # PNG starts with top row, whereas native mask values start at bottom.
            self.assertEqual(rows, b"\0" + bytes((255, 255, 255, 0, 255, 255, 255, 255))
                             + b"\0" + bytes((255, 255, 255, 255, 255, 255, 255, 0)))


@unittest.skipUnless(os.environ.get("MESHVENN_CHARACTER_QUALITY_OUTPUT"), "real Blender output not configured")
class CompletedReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ["MESHVENN_CHARACTER_QUALITY_OUTPUT"]).resolve()
        cls.manifest = json.loads((cls.output / "manifest.json").read_text(encoding="utf-8"))

    def test_all_declared_assets_are_exact_and_within_output(self):
        def visit(value):
            if isinstance(value, dict):
                if set(value) == {"path", "sha256", "bytes"}:
                    path = (self.output / value["path"]).resolve()
                    self.assertTrue(path.is_relative_to(self.output))
                    data = path.read_bytes()
                    self.assertEqual(len(data), value["bytes"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), value["sha256"])
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(self.manifest)
        self.assertTrue(self.manifest["complete"])
        self.assertEqual(len(self.manifest["cases"]), 2 * len(self.manifest["requested"]["view_counts"]))

    def test_candidate_is_actual_reconstruction_not_source_or_normals_only(self):
        m = self.manifest
        source_sha = m["source"]["glb"]["sha256"]
        self.assertEqual(source_sha, m["source"]["original_sha256"])
        self.assertFalse(m["scope"]["rig_certified"])
        self.assertFalse(m["scope"]["source_mesh_used_for_candidate_fit"])
        self.assertFalse(m["comparison_frame"]["source_fit"])
        cases = {c["id"]: c for c in m["cases"]}
        for count in m["requested"]["view_counts"]:
            raw, organic = (cases[f"views{count:02d}_{finish}"] for finish in ("none", "organic"))
            self.assertEqual(raw["native_volume"], organic["native_volume"])
            self.assertGreater(raw["native_volume"]["occupied_voxels"], 0)
            self.assertEqual(raw["native_mesh"]["indices_sha256"], organic["native_mesh"]["indices_sha256"])
            self.assertNotEqual(raw["native_mesh"]["vertices_sha256"], organic["native_mesh"]["vertices_sha256"])
            detail = organic["refinement"]
            self.assertEqual(detail["algorithm"], "contour-taubin-v2")
            self.assertTrue(detail["topology_preserved"])
            self.assertTrue(detail["face_orientation_preserved"])
            self.assertLessEqual(detail["maximum_displacement_in_voxels"], .750001)
            self.assertLessEqual(detail["maximum_component_volume_drift"], .020001)
            for case in (raw, organic):
                with self.subTest(case=case["id"]):
                    self.assertNotEqual(case["glb"]["sha256"], source_sha)
                    self.assertEqual(case["reload"]["source_glb_sha256"], case["glb"]["sha256"])
                    self.assertTrue(case["reload"]["reloaded_in_empty_scene"])
                    self.assertTrue(case["reload"]["verified"])
                    self.assertGreater(case["reload"]["triangles"], 0)
                    self.assertLessEqual(case["reload"]["maximum_bounds_error"], 3e-6)
                    self.assertEqual(case["canonical_transform"]["scale"], 2 / case["resolution"])
                    self.assertEqual(case["canonical_transform"]["translation"], [0, 0, -1])
                    self.assertFalse(case["canonical_transform"]["per_case_fit"])
                    self.assertEqual((self.output / case["glb"]["path"]).read_bytes()[:4], b"glTF")

    def test_generator_and_core_authority_are_the_executed_files(self):
        for record in self.manifest["generator"]["source_files"] + self.manifest["implementation_sources"]:
            with self.subTest(path=record["path"]):
                self.assertEqual(hashlib.sha256((ROOT / record["path"]).read_bytes()).hexdigest(), record["sha256"])
        for camera in self.manifest["cameras"]:
            self.assertLessEqual(camera["maximum_native_uv_error"], 2e-6)
            self.assertGreater(camera["foreground_pixels"], 0)
            self.assertFalse(camera["flip_x"])


if __name__ == "__main__":
    unittest.main()
