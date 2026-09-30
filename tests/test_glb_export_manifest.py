from __future__ import annotations

import json
import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "implementations" / "glb_export" / "manifest.py"
SPEC = importlib.util.spec_from_file_location("glb_export_manifest", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load GLB manifest module")
manifest_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = manifest_module
SPEC.loader.exec_module(manifest_module)
inspect_glb = manifest_module.inspect_glb


def _glb(document: dict) -> bytes:
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    length = 12 + 8 + len(encoded)
    return (
        struct.pack("<4sII", b"glTF", 2, length)
        + struct.pack("<II", len(encoded), 0x4E4F534A)
        + encoded
    )


class GLBManifestTests(unittest.TestCase):
    def test_inspects_valid_glb_manifest_and_hash(self) -> None:
        document = {
            "asset": {"version": "2.0"},
            "scenes": [{"nodes": [0, 1]}],
            "nodes": [{"name": "Character"}, {"name": "Armature"}],
            "meshes": [{}],
            "skins": [{}],
            "materials": [{}, {}],
            "animations": [{"name": "Walk"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character.glb"
            path.write_bytes(_glb(document))
            manifest = inspect_glb(path)

        self.assertEqual(manifest.version, 2)
        self.assertEqual(manifest.node_names, ("Character", "Armature"))
        self.assertEqual(manifest.animation_names, ("Walk",))
        self.assertEqual(manifest.scene_count, 1)
        self.assertEqual(manifest.mesh_count, 1)
        self.assertEqual(manifest.skin_count, 1)
        self.assertEqual(manifest.material_count, 2)
        self.assertEqual(len(manifest.sha256), 64)

    def test_rejects_corrupt_or_non_gltf_2_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.glb"
            path.write_bytes(b"not a glb")
            with self.assertRaises(ValueError):
                inspect_glb(path)

            path.write_bytes(_glb({"asset": {"version": "1.0"}}))
            with self.assertRaises(ValueError):
                inspect_glb(path)

    def test_rejects_duplicate_animation_names(self) -> None:
        document = {
            "asset": {"version": "2.0"},
            "animations": [{"name": "Walk"}, {"name": "Walk"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.glb"
            path.write_bytes(_glb(document))
            with self.assertRaises(ValueError):
                inspect_glb(path)


if __name__ == "__main__":
    unittest.main()
