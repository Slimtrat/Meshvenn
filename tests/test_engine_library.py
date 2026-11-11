"""Public facade contracts and real native execution, without Blender or SDKs."""
from __future__ import annotations

import base64
import json
import os
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from meshvenn_engine import EngineError, MeshvennEngine
from meshvenn_engine.core.diagnostic_contracts import ArtifactReference, CameraDeclaration, ViewRevision, ViewSetRevision
from meshvenn_engine.core.diagnostics_preflight import RasterInput
from meshvenn_engine.core.geometry_diagnostics import GeometryResult, VolumeArtifact


def cube_arguments():
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
    rows = []
    for y in reversed(range(31)):
        rows.append(b"\0" + bytes(channel for x in range(31)
            for channel in ((80, 130, 210, 255) if 7 <= x <= 23 and 7 <= y <= 23 else (0, 0, 0, 0))))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 31, 31, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
    raster = RasterInput.from_png_bytes(png)
    proof = ArtifactReference("analytic-proof", "a" * 64, "application/json")
    views = tuple(ViewRevision(name, 1, raster.content_reference(), None,
        CameraDeclaration("orthographic", angle, 0, verified=True, verification_evidence=proof),
        origin="rendered") for name, angle in (("front", 0), ("side", 90)))
    return {"view_set": ViewSetRevision("cube", 1, views).to_dict(),
        "inputs": {view.view_id: {"image": {"png_base64": base64.b64encode(png).decode()}} for view in views}}


def library():
    value = os.environ.get("MESHVENN_TEST_NATIVE_LIBRARY") or os.environ.get("MESHVENN_TEST_NATIVE_DLL")
    return Path(value) if value else None


class EngineLibraryTests(unittest.TestCase):
    def test_isolated_import_and_catalogue_have_no_blender_or_provider_dependency(self):
        code = "import sys,json;sys.path.insert(0,sys.argv[1]);from meshvenn_engine import MeshvennEngine;print(json.dumps(MeshvennEngine().capabilities()));assert 'bpy' not in sys.modules;assert not any(n.startswith(('openai','mcp','anthropic')) for n in sys.modules)"
        child = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT / "lib")],
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
        catalogue = json.loads(child.stdout)
        self.assertEqual(set(catalogue["actions"]), {"engine.capabilities", "views.preflight", "geometry.diagnose", "geometry.mesh"})
        for descriptor in catalogue["actions"].values():
            self.assertEqual(descriptor["version"], 1)
            self.assertIs(type(descriptor["available"]), bool)
            self.assertEqual(descriptor["input_schema"]["additionalProperties"], False)

    def test_png_preflight_reuses_real_hash_dimension_and_camera_checks(self):
        engine = MeshvennEngine()
        arguments = cube_arguments()
        arguments["policy"] = {"required_cameras": []}
        result = engine.execute("views.preflight", arguments)
        self.assertEqual(result["verification_status"], "unknown")  # Independent registration anchors are absent.
        self.assertTrue(any(f["code"] == "input.integrity" and f["status"] == "pass" for f in result["report"]["findings"]))
        bad = json.loads(json.dumps(arguments))
        bad["view_set"]["views"][0]["image"]["sha256"] = "b" * 64
        self.assertEqual(engine.execute("views.preflight", bad)["verification_status"], "fail")

    def test_rgba_buffers_use_the_core_canonical_source_fingerprint(self):
        rgba = [0, 0, 0, 0] * 16
        raster = RasterInput.from_pixels(4, 4, rgba)
        arguments = cube_arguments()
        for view in arguments["view_set"]["views"]:
            view["image"] = raster.content_reference().to_dict()
            arguments["inputs"][view["view_id"]] = {"image": {"width": 4, "height": 4, "rgba": rgba}}
        result = MeshvennEngine().execute("views.preflight", arguments)
        self.assertTrue(any(f["code"] == "input.empty_alpha" for f in result["report"]["findings"]))
        self.assertFalse(any(f["code"] == "input.hash_mismatch" for f in result["report"]["findings"]))

    def test_tool_arguments_cannot_choose_native_paths_or_execute_code(self):
        engine = MeshvennEngine()
        for name in ("native_library", "python_executable", "command", "path", "code"):
            with self.subTest(name=name), self.assertRaises(EngineError) as caught:
                engine.execute("geometry.diagnose", {**cube_arguments(), name: "untrusted"})
            self.assertEqual(caught.exception.code, "invalid_arguments")
        with self.assertRaises(EngineError) as caught:
            engine.execute("pipeline.run", {})
        self.assertEqual(caught.exception.code, "unknown_action")

    def test_ambiguous_rasters_nonjson_values_and_forged_volumes_fail_before_native(self):
        for value in ({"png_base64": "aA==", "width": 1}, {"png_base64": "!"},
                      {"width": True, "height": 1, "rgba": [0, 0, 0, 0]},
                      {"width": 1, "height": 1, "rgba": [float("nan"), 0, 0, 1]}):
            arguments = cube_arguments()
            arguments["inputs"]["front"]["image"] = value
            with self.subTest(value=value), self.assertRaises(EngineError):
                MeshvennEngine().execute("views.preflight", arguments)
        with self.assertRaises(EngineError):
            MeshvennEngine().execute("geometry.mesh", {"volume": {"width": 64}})

    def test_cancellation_and_unavailable_native_remain_explicit(self):
        engine = MeshvennEngine(native_library=ROOT / "no-native-library.dll")
        self.assertFalse(engine.capabilities()["actions"]["geometry.diagnose"]["available"])
        with self.assertRaises(EngineError) as caught:
            engine.execute("views.preflight", cube_arguments(), cancel=lambda: True)
        self.assertEqual(caught.exception.code, "cancelled")
        result = engine.execute("geometry.diagnose", cube_arguments())
        self.assertEqual(result["verification_status"], "unknown")
        self.assertTrue(any(f["code"] == "engine.native_unavailable" for f in result["report"]["findings"]))

    def test_core_cancelled_report_and_attempt_history_are_returned_without_discarding_evidence(self):
        calls = 0
        def cancel():
            nonlocal calls
            calls += 1
            return calls >= 2  # Facade permits dispatch; cancellation occurs inside D3.
        result = MeshvennEngine().execute("geometry.diagnose", cube_arguments(), cancel=cancel)
        self.assertEqual(result["verification_status"], "unknown")
        self.assertEqual(result["report"]["completion"], "cancelled")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["attempts"][0]["report"]["completion"], "cancelled")


@unittest.skipUnless(library(), "Set MESHVENN_TEST_NATIVE_LIBRARY for real native facade tests.")
class EngineLibraryNativeTests(unittest.TestCase):
    def test_actual_diagnostic_then_isolated_surface_mesh_and_strict_roundtrip(self):
        engine = MeshvennEngine(library(), sys.executable)
        arguments = cube_arguments()
        arguments["policy"] = {"resolution": 16, "reprojection_size": 64, "max_seconds": 15}
        result = engine.execute("geometry.diagnose", arguments)
        self.assertEqual(result["verification_status"], "pass")
        status = result.pop("verification_status")
        self.assertEqual(GeometryResult.from_dict(result).report.verification_status, status)
        self.assertGreater(result["volume"]["occupied_count"], 0)
        for mode in ("blocks", "surface-nets"):
            with self.subTest(mode=mode):
                mesh = engine.execute("geometry.mesh", {"volume": result["volume"], "mesh_mode": mode})
                self.assertEqual(mesh["verification_status"], "unknown")
                self.assertGreater(mesh["mesh"]["vertex_count"], 0)
                self.assertNotEqual(mesh["provenance"]["worker_pid"], os.getpid())
                self.assertEqual(mesh["provenance"]["source_volume_sha256"], result["volume"]["sha256"])
                json.dumps(mesh, allow_nan=False)

    def test_native_mesh_deadline_reaps_child_and_reports_timeout(self):
        engine = MeshvennEngine(library(), sys.executable)
        volume = VolumeArtifact(8, 8, 8, "00" * 512, 0, None, VolumeArtifact.digest(8, bytes(512)))
        with self.assertRaises(EngineError) as caught:
            engine.execute("geometry.mesh", {"volume": volume.to_dict(), "max_seconds": .001})
        self.assertEqual(caught.exception.code, "timeout")


if __name__ == "__main__":
    unittest.main()
