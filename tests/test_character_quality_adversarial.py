"""Independent source/cache binding regressions, before any Blender dispatch.

These tests qualify orchestration validation only. The renderer is deliberately
stopped at its boundary; no generated character or aesthetic verdict is mocked.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.character_quality.workflow import qualify_characters


class RenderBoundaryReached(RuntimeError):
    pass


def triangle_glb(x=0.0):
    """Small valid, embedded-buffer GLB; differing positions change its SHA."""
    binary = struct.pack("<9f3H", x, 0., 0., x + 1., 0., 0., x, 1., 0., 0, 1, 2)
    document = {
        "asset": {"version": "2.0"}, "scene": 0,
        "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                        {"buffer": 0, "byteOffset": 36, "byteLength": 6}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                       "min": [x, 0, 0], "max": [x + 1, 1, 0]},
                      {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = (struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
              + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def build_cache(root):
    root.mkdir()

    def asset(name, data):
        (root / name).write_bytes(data)
        return {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    source = asset("source.glb", triangle_glb())
    candidate = asset("candidate.glb", triangle_glb(.125))
    # Valid one-pixel PNG; only its byte integrity is evaluated before dispatch.
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVioAAAAASUVORK5CYII=")
    hero = asset("hero.png", png)
    case = {"id": "views02_none", "resolution": 64, "surface_refinement": "none",
            "view_ids": ["az000", "az090"], "glb": candidate, "hero": hero,
            "reload": {"verified": True, "source_glb_sha256": candidate["sha256"]},
            "canonical_transform": {"per_case_fit": False}}
    manifest = {"schema_version": 1, "complete": True,
                "source": {"role": "source", "original_sha256": source["sha256"],
                           "glb": source, "hero": hero,
                           "reload": {"verified": True, "source_glb_sha256": source["sha256"]}},
                "cases": [case], "cameras": [{"png": hero}, {"png": hero}]}
    (root / "views02_none.json").write_text(json.dumps(case), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root / "manifest.json", source["sha256"]


class ExplicitSourceCacheBindingTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "tmp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="source-binding-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest, self.source_sha = build_cache(self.root / "cache")
        self.original_cache = {p.name: p.read_bytes() for p in self.manifest.parent.iterdir()}

    def run_to_render_boundary(self, explicit_source):
        return qualify_characters(self.root / "qualification", blender_executable=sys.executable,
                                  from_reconstruction=(self.manifest,), source_glb=explicit_source)

    def assert_failure_preserved(self):
        result = json.loads((self.root / "qualification/qualification.json").read_text(encoding="utf-8"))
        self.assertEqual(result["technical_status"], "failed")
        self.assertEqual(result["quality_certification"], "unknown")
        self.assertEqual(result["stages"], [])
        self.assertEqual(self.original_cache,
                         {p.name: p.read_bytes() for p in self.manifest.parent.iterdir()})

    def test_missing_explicit_source_rejected_before_render(self):
        with patch("scripts.character_quality.workflow.render_comparison",
                   side_effect=RenderBoundaryReached("render must not start")) as render:
            with self.assertRaises(FileNotFoundError):
                self.run_to_render_boundary(self.root / "missing.glb")
        render.assert_not_called()
        self.assert_failure_preserved()

    def test_foreign_valid_glb_rejected_before_render(self):
        foreign = self.root / "different-source.glb"
        foreign.write_bytes(triangle_glb(.5))
        self.assertNotEqual(hashlib.sha256(foreign.read_bytes()).hexdigest(), self.source_sha)
        with patch("scripts.character_quality.workflow.render_comparison",
                   side_effect=RenderBoundaryReached("render must not start")) as render:
            with self.assertRaisesRegex(ValueError, "explicitly requested source GLB"):
                self.run_to_render_boundary(foreign)
        render.assert_not_called()
        self.assert_failure_preserved()

    def test_identical_source_at_another_path_reaches_render(self):
        explicit = self.root / "requested-source.glb"
        explicit.write_bytes((self.manifest.parent / "source.glb").read_bytes())
        with patch("scripts.character_quality.workflow.render_comparison",
                   side_effect=RenderBoundaryReached("accepted source")) as render:
            with self.assertRaisesRegex(RenderBoundaryReached, "accepted source"):
                self.run_to_render_boundary(explicit)
        render.assert_called_once()
        assets = render.call_args.args[0]
        self.assertEqual(assets[0]["role"], "source")
        self.assertEqual(assets[0]["glb_sha256"], self.source_sha)
        self.assertEqual(self.original_cache,
                         {p.name: p.read_bytes() for p in self.manifest.parent.iterdir()})


if __name__ == "__main__":
    unittest.main()
