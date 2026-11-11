"""Engine boundaries plus real isolated NativeCore integration where available."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from core.diagnostic_contracts import ArtifactReference, CameraDeclaration, Region, ViewRevision, ViewSetRevision
from core.diagnostics_preflight import RasterInput, ViewInput
from core.geometry_diagnostics import GeometryPolicy, GeometryResult, NativeGeometryBackend, VolumeArtifact, analyze_geometry
from core.image_mask import BinaryMask
from core.native_bridge import NativeProjection, NativeVolume


def sources(*, angles=(0, 90), size=32, empty=False, disjoint=False):
    proof = ArtifactReference("analytic-camera", "a" * 64, "application/json")
    views, inputs = [], {}
    for index, angle in enumerate(angles):
        name = f"v{index}"
        def occupied(x, y):
            if empty:
                return False
            return 5 <= x < size-5 and ((3 <= y < 9) if disjoint and index == 0 else
                                      (size-9 <= y < size-3) if disjoint else 5 <= y < size-5)
        rgba = tuple(value for y in range(size) for x in range(size)
                     for value in ((1., 1., 1., 1.) if occupied(x, y) else (0., 0., 0., 0.)))
        raster = RasterInput.from_pixels(size, size, rgba, source_bytes=f"independent-source-{index}".encode())
        camera = CameraDeclaration("orthographic", angle, 0, verified=True, verification_evidence=proof)
        views.append(ViewRevision(name, 1, raster.content_reference(), raster.content_reference(), camera))
        inputs[name] = ViewInput(raster, raster)
    return ViewSetRevision("analytic-box", 1, tuple(views)), inputs


def native_library():
    configured = os.environ.get("MESHVENN_TEST_NATIVE_LIBRARY")
    if configured:
        return Path(configured)
    for root in Path(__file__).resolve().parents:
        candidate = root / "native" / "bin" / ("bpt_core.dll" if os.name == "nt" else "libbpt_core.so")
        if candidate.is_file():
            return candidate
    return None


LIBRARY = native_library()


class GeometryBoundaryTests(unittest.TestCase):
    def test_policy_rejects_nonfinite_and_unbounded_values(self):
        for kwargs in ({"max_seconds": float("nan")}, {"max_seconds": float("inf")},
                       {"resolution": 128}, {"resolution": True}, {"thread_count": True}, {"max_views": 11}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                GeometryPolicy(**kwargs)

    def test_backend_rejects_nonfinite_deadline_before_launch(self):
        backend = NativeGeometryBackend(Path("missing.dll"))
        with patch("core.geometry_diagnostics.backend.subprocess.Popen") as launch:
            for value in (float("nan"), float("inf"), float("-inf"), True):
                with self.assertRaises(ValueError):
                    backend.run((), resolution=32, input_order=(), timeout=value)
            launch.assert_not_called()

    def test_backend_rejects_duplicate_order_and_noninteger_threads(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "unused.dll"
            library.write_bytes(b"bounded validation only")
            backend = NativeGeometryBackend(library)
            projection = NativeProjection(BinaryMask(2, 2, b"\1" * 4), 0)
            with patch("core.geometry_diagnostics.backend.subprocess.Popen") as launch:
                with self.assertRaises(ValueError):
                    backend.run((("a", projection),), resolution=32, input_order=("a", "a"), timeout=1)
                for count in (True, 1.5):
                    with self.assertRaises(ValueError):
                        backend.run((("a", projection),), resolution=32, input_order=("a",), timeout=1, thread_count=count)
                launch.assert_not_called()

    def test_volume_rejects_forged_occupancy_bounds(self):
        values = b"\1" + b"\0" * (8 ** 3 - 1)
        correct = VolumeArtifact.from_native(NativeVolume(8, 8, 8, values, 1, (0, 0, 0, 0, 0, 0)))
        with self.assertRaises(ValueError):
            replace(correct, bounds=(0, 7, 0, 7, 0, 7))

    def test_blocked_native_child_is_terminated_and_reaped_on_deadline(self):
        class BlockedChild:
            returncode = None
            terminated = False
            reaped = False
            def poll(self):
                return self.returncode
            def wait(self, timeout=None):
                if self.returncode is not None:
                    self.reaped = True
                    return self.returncode
                time.sleep(min(timeout or .001, .005))
                raise subprocess.TimeoutExpired("safe mocked native child", timeout)
            def terminate(self):
                self.terminated = True
                self.returncode = -1
            def kill(self):
                self.returncode = -9
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "unused.dll"
            library.write_bytes(b"safe mocked backend fixture")
            backend = NativeGeometryBackend(library)
            child = BlockedChild()
            projection = NativeProjection(BinaryMask(2, 2, b"\1" * 4), 0)
            with patch("core.geometry_diagnostics.backend.subprocess.Popen", return_value=child):
                result = backend.run((("a", projection),), resolution=8, input_order=("a",), timeout=.02)
        self.assertEqual(result.state, "time_budget")
        self.assertEqual(result.termination, "terminated_deadline")
        self.assertTrue(child.terminated)
        self.assertTrue(child.reaped)

    def test_worker_tempfile_os_failure_is_a_structured_result(self):
        with patch.object(NativeGeometryBackend, "_run", side_effect=PermissionError("test denied temp access")):
            result = NativeGeometryBackend().run((), resolution=8, input_order=(), timeout=1)
        self.assertEqual(result.state, "worker_failure")
        self.assertIn("PermissionError", result.error)

    def test_malformed_input_never_launches_native(self):
        revision, inputs = sources()
        wrong = replace(inputs["v0"].image, source_sha256="b" * 64)
        inputs = {key: ViewInput(wrong, wrong) for key in inputs}
        with patch.object(NativeGeometryBackend, "run") as run:
            result = analyze_geometry(revision, inputs)
        run.assert_not_called()
        self.assertEqual(result.report.verification_status, "fail")
        self.assertTrue(any(f.code == "input.hash_mismatch" for f in result.report.findings))

    def test_absent_backend_is_distinct_from_empty_geometry(self):
        revision, inputs = sources()
        result = analyze_geometry(revision, inputs, backend=NativeGeometryBackend(Path("missing-diagnostic-library.dll")))
        self.assertEqual(result.report.completion, "failed")
        self.assertIsNone(result.volume)
        self.assertTrue(any(f.code == "engine.native_unavailable" for f in result.report.findings))
        self.assertFalse(any(f.code == "geometry.empty" for f in result.report.findings))

    def test_blender_binary_is_not_treated_as_python(self):
        revision, inputs = sources()
        result = analyze_geometry(revision, inputs, backend=NativeGeometryBackend(python_executable=Path("blender.exe")))
        self.assertTrue(any(f.code == "engine.host_unavailable" for f in result.report.findings))

    def test_cancelled_analysis_does_not_claim_pass(self):
        revision, inputs = sources()
        result = analyze_geometry(revision, inputs, cancel=lambda: True)
        self.assertEqual(result.report.completion, "cancelled")
        self.assertEqual(result.report.verification_status, "unknown")

    def test_missing_backend_result_roundtrips_with_named_region(self):
        revision, inputs = sources()
        result = analyze_geometry(revision, inputs, regions=(Region("v0", "empty-region", (0., 0., .1, .1)),),
                                  backend=NativeGeometryBackend(Path("missing-diagnostic-library.dll")))
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)


@unittest.skipUnless(LIBRARY, "Real native library unavailable; integration is not simulated.")
class GeometryNativeTests(unittest.TestCase):
    def backend(self):
        return NativeGeometryBackend(LIBRARY, python_executable=Path(sys.executable))

    def test_real_native_pass_roundtrip_and_missing_anchor_not_a_gate(self):
        revision, inputs = sources()
        result = analyze_geometry(revision, inputs, backend=self.backend())
        self.assertEqual(result.report.verification_status, "pass")
        self.assertEqual(result.provenance.completed_experiments, 3)
        self.assertGreater(result.volume.occupied_count, 0)
        self.assertTrue(any(f.code == "alignment.reference_missing" and f.status == "unknown" and not f.required for f in result.report.findings))
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)

    def test_real_empty_named_region_is_unknown_and_roundtrips(self):
        revision, inputs = sources()
        region = Region("v0", "empty-region", (0., 0., .1, .1))
        result = analyze_geometry(revision, inputs, regions=(region,), backend=self.backend())
        self.assertTrue(any(f.code == "geometry.detail_preservation" and region in f.regions and f.status == "unknown"
                            for f in result.report.findings))
        self.assertIsNone(result.views[0].metrics.important_regions[0].recall)
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)

    def test_real_native_permutation_preserves_final_conclusions(self):
        revision, inputs = sources(angles=(0, 90, 180))
        first = analyze_geometry(revision, inputs, backend=self.backend())
        second = analyze_geometry(replace(revision, input_order=tuple(reversed(revision.input_order))), inputs, backend=self.backend())
        self.assertEqual(first.volume, second.volume)
        conclusion = lambda r: [(f.code, f.status, f.view_ids, f.regions) for f in r.report.findings if f.category in ("geometry", "coverage")]
        self.assertEqual(conclusion(first), conclusion(second))
        self.assertEqual(first.report.dependency_fingerprint, second.report.dependency_fingerprint)
        self.assertNotEqual(first.trace[0].view_id, second.trace[0].view_id)

    def test_real_native_nonempty_masks_empty_hull_is_not_engine_failure(self):
        revision, inputs = sources(disjoint=True)
        result = analyze_geometry(revision, inputs, backend=self.backend())
        self.assertEqual(result.volume.occupied_count, 0)
        self.assertTrue(any(f.code == "geometry.empty" and f.status == "fail" for f in result.report.findings))
        self.assertEqual(result.report.completion, "complete")

    def test_real_one_view_counterfactual_is_supported_but_coverage_unknown(self):
        revision, inputs = sources(angles=(0,))
        result = analyze_geometry(revision, inputs, backend=self.backend())
        self.assertEqual(result.provenance.completed_experiments, 1)
        self.assertGreater(result.volume.occupied_count, 0)
        self.assertTrue(any(f.code == "coverage.insufficient" and f.status == "unknown" for f in result.report.findings))

    def test_real_dll_load_failure_is_explicit(self):
        revision, inputs = sources()
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / ("bad.dll" if os.name == "nt" else "bad.so")
            library.write_bytes(b"not a native binary")
            result = analyze_geometry(revision, inputs, backend=NativeGeometryBackend(library, python_executable=Path(sys.executable)))
        self.assertEqual(result.report.completion, "failed")
        self.assertTrue(any(f.code == "engine.native_failure" for f in result.report.findings))


if __name__ == "__main__":
    unittest.main()
