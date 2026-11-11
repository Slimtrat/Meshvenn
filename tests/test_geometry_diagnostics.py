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

from core.diagnostic_contracts import ArtifactReference, CameraDeclaration, CanonicalReference, Region, ViewRevision, ViewSetRevision
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


def thin_sources(size=64):
    """Analytic opaque slab whose side falls between the 32-grid samples."""
    revision, inputs = sources(angles=(0, 90, 180, 270), size=size)
    updated = []
    scale = size // 64
    for index, view in enumerate(revision.views):
        rgba = tuple(value for y in range(size) for x in range(size)
                     for value in ((1., 1., 1., 1.) if 10*scale <= y < 54*scale and
                                   ((10*scale <= x < 54*scale) if index % 2 == 0 else 31*scale <= x < 33*scale)
                                   else (0., 0., 0., 0.)))
        raster = RasterInput.from_pixels(size, size, rgba, source_bytes=f"analytic-thin-{size}-{index}".encode())
        inputs[view.view_id] = ViewInput(raster, raster)
        updated.append(replace(view, image=raster.content_reference(), mask=raster.content_reference()))
    return replace(revision, views=tuple(updated)), inputs


class GeometryBoundaryTests(unittest.TestCase):
    def test_policy_rejects_nonfinite_and_unbounded_values(self):
        for kwargs in ({"max_seconds": float("nan")}, {"max_seconds": float("inf")},
                       {"resolution": 128}, {"resolution": True}, {"thread_count": True}, {"max_views": 11},
                       {"adaptive_refinement": 1}, {"refinement_resolution": 128}, {"max_total_experiments": 25},
                       {"max_total_python_work": 8_000_000_001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                GeometryPolicy(**kwargs)

    def test_source_hash_binds_shared_runtime_authorities_and_is_stable(self):
        from core.geometry_diagnostics.engine import _source_hash
        before = _source_hash()
        self.assertEqual(before, _source_hash())
        read_bytes = Path.read_bytes
        for suffix in ("diagnostic_contracts/reports.py", "diagnostics_preflight/rasters.py", "image_mask.py", "native_loader.py"):
            def changed(path):
                content = read_bytes(path)
                return content+b"\n# dependency probe\n" if path.as_posix().endswith(suffix) else content
            with self.subTest(suffix=suffix), patch.object(Path, "read_bytes", changed):
                self.assertNotEqual(before, _source_hash())

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

    def test_adaptive_empty_grid_retains_initial_and_bounds_shared_execution(self):
        class RecordingBackend(NativeGeometryBackend):
            def __init__(self):
                super().__init__(LIBRARY, python_executable=Path(sys.executable))
                self.timeouts = []
            def run(self, *args, **kwargs):
                self.timeouts.append(kwargs["timeout"])
                return super().run(*args, **kwargs)
        backend = RecordingBackend()
        revision, inputs = thin_sources()
        policy = GeometryPolicy()
        result = analyze_geometry(revision, inputs, policy=policy, backend=backend)
        self.assertEqual((result.requested_resolution, result.actual_resolution), (32, 64))
        self.assertEqual(tuple(a.resolution for a in result.attempts), (32, 64))
        self.assertEqual(result.attempts[0].volume.occupied_count, 0)
        self.assertTrue(any(f.code == "geometry.empty" and f.status == "fail" for f in result.attempts[0].report.findings))
        self.assertGreater(result.volume.occupied_count, 0)
        self.assertTrue(all(a.report.policy == policy.contract() for a in result.attempts))
        self.assertEqual(result.report.policy, policy.contract())
        self.assertEqual(result.attempts[0].provenance.source_sha256, result.attempts[1].provenance.source_sha256)
        self.assertEqual(len(backend.timeouts), 2)
        self.assertLess(backend.timeouts[1], backend.timeouts[0])
        self.assertEqual(result.provenance.completed_experiments, sum(a.provenance.completed_experiments for a in result.attempts))
        self.assertEqual(result.provenance.native_sessions_reserved, sum(a.provenance.native_sessions_reserved for a in result.attempts))
        self.assertLessEqual(result.provenance.native_sessions_reserved, policy.max_total_experiments)
        self.assertLessEqual(result.provenance.native_voxel_test_capacity, policy.max_total_native_voxel_tests)
        self.assertLessEqual(result.provenance.python_work_reserved, policy.max_total_python_work)
        self.assertTrue(all(f.status == "pass" for f in result.report.findings if f.code == "geometry.cross_view_conflict"))
        self.assertFalse(any(f.code == "geometry.attribution" for f in result.report.findings))
        self.assertTrue(any(f.code == "geometry.sampled_component_coverage" and f.status == "pass" for f in result.report.findings))
        self.assertTrue(any(f.code == "geometry.detail_preservation" and f.status == "unknown" for f in result.report.findings))
        self.assertGreater(max(1-step.after/step.before for step in result.trace if step.before), .95)
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)
        tampered = result.to_dict()
        tampered["attempts"].append(tampered["attempts"][-1])
        with self.assertRaises(ValueError):
            GeometryResult.from_dict(tampered)

    def test_within_uncertainty_compatibility_retains_low_raw_iou_and_unknown_physical_detail(self):
        revision, inputs = thin_sources(size=128)
        result = analyze_geometry(revision, inputs, backend=self.backend())
        side = next(v for v in result.views if v.view_id == "v1")
        self.assertLess(side.metrics.iou, .9)
        self.assertEqual(side.metrics.missing_beyond_tolerance_pixels+side.metrics.extraneous_beyond_tolerance_pixels, 0)
        self.assertTrue(side.metrics.component_correspondence)
        self.assertTrue(all(f.status == "pass" for f in result.report.findings if f.code == "geometry.cross_view_conflict"))
        self.assertEqual(side.metrics.components[0].status, "unknown")
        self.assertEqual(result.report.verification_status, "unknown")

    def test_adaptive_aggregate_budget_stops_second_attempt_without_erasing_initial(self):
        revision, inputs = thin_sources()
        result = analyze_geometry(revision, inputs, backend=self.backend(), policy=GeometryPolicy(max_total_experiments=6))
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0].volume.occupied_count, 0)
        self.assertEqual(result.report.completion, "partial")
        self.assertEqual(result.report.verification_status, "unknown")
        self.assertTrue(any(f.code == "engine.refinement" and f.status == "unknown" for f in result.report.findings))
        self.assertTrue(any(f.code == "geometry.empty" and f.status == "fail" for f in result.attempts[0].report.findings))
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)

    def test_adaptive_can_be_disabled_and_never_retries_at_64(self):
        revision, inputs = thin_sources()
        disabled = analyze_geometry(revision, inputs, backend=self.backend(), policy=GeometryPolicy(adaptive_refinement=False))
        self.assertEqual(len(disabled.attempts), 1)
        self.assertEqual(disabled.actual_resolution, 32)
        ceiling = analyze_geometry(revision, inputs, backend=self.backend(), policy=GeometryPolicy(resolution=64))
        self.assertEqual(len(ceiling.attempts), 1)
        self.assertEqual(ceiling.actual_resolution, 64)

    def test_cancelled_second_attempt_is_unknown_and_preserves_first(self):
        from core.geometry_diagnostics.backend import NativeBatch
        class CancelSecond(NativeGeometryBackend):
            def __init__(self):
                super().__init__(LIBRARY, python_executable=Path(sys.executable))
                self.completed_first = None
            def run(self, *args, **kwargs):
                if self.completed_first is None:
                    self.completed_first = super().run(*args, **kwargs)
                    return self.completed_first
                first = self.completed_first
                return NativeBatch((), "cancelled", "Controlled second-attempt cancellation orchestration test.",
                                   first.library_sha256, first.python_executable, .001, "terminated_cancelled")
        revision, inputs = thin_sources()
        result = analyze_geometry(revision, inputs, backend=CancelSecond())
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(result.attempts[0].report.completion, "complete")
        self.assertEqual(result.attempts[0].volume.occupied_count, 0)
        self.assertEqual(result.attempts[1].report.completion, "cancelled")
        self.assertEqual(result.report.completion, "cancelled")
        self.assertEqual(result.report.verification_status, "unknown")
        self.assertTrue(any(f.code == "engine.refinement" and f.status == "unknown" and "did not complete" in f.message for f in result.report.findings))
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)

    def test_real_second_worker_deadline_is_unknown_and_preserves_first(self):
        class DeadlineSecond(NativeGeometryBackend):
            calls = 0
            def run(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 2:
                    kwargs["timeout"] = min(kwargs["timeout"], .02)
                return super().run(*args, **kwargs)
        revision, inputs = thin_sources()
        backend = DeadlineSecond(LIBRARY, python_executable=Path(sys.executable))
        result = analyze_geometry(revision, inputs, backend=backend)
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(result.attempts[0].report.completion, "complete")
        self.assertEqual(result.attempts[1].report.completion, "partial")
        self.assertEqual(result.report.verification_status, "unknown")
        self.assertTrue(any(f.code == "engine.refinement" and f.status == "unknown" for f in result.report.findings))
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)

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

    def test_real_native_keeps_megapixel_source_and_bounds_measurement_grid(self):
        revision, inputs = sources(angles=(0,), size=1024)
        result = analyze_geometry(revision, inputs, backend=self.backend())
        self.assertEqual(result.report.completion, "complete")
        self.assertEqual(result.views[0].source_width, 1024)
        self.assertEqual(result.views[0].source_height, 1024)
        self.assertEqual(result.views[0].expected.width, 256)
        self.assertEqual(result.report.view_set.views[0].mask.width, 1024)
        self.assertEqual(inputs["v0"].mask.width, 1024)
        self.assertGreater(result.volume.occupied_count, 0)
        self.assertNotEqual(result.views[0].aligned_mask_sha256, result.views[0].expected.sha256)

    def test_direct_antipodal_detail_failure_does_not_overstate_coarse_native_roi(self):
        revision, inputs = sources(angles=(0, 90, 180, 270), size=64)
        updated = []
        for view in revision.views:
            rgba = tuple(value for y in range(64) for x in range(64)
                         for value in ((1., 1., 1., 1.) if (18 <= x < 46 and 14 <= y < 42) or
                                       (view.view_id == "v0" and 44 <= x < 46 and 49 <= y < 54)
                                       else (0., 0., 0., 0.)))
            raster = RasterInput.from_pixels(64, 64, rgba, source_bytes=("part-"+view.view_id).encode())
            inputs[view.view_id] = ViewInput(raster, raster)
            updated.append(replace(view, image=raster.content_reference(), mask=raster.content_reference()))
        revision = replace(revision, views=tuple(updated))
        reference_source = inputs["v1"].mask
        reference_raster = RasterInput.from_pixels(64, 64, reference_source.rgba, source_bytes=b"independent-original-reference")
        reference = ViewRevision("ref-v0", 1, reference_raster.content_reference(), reference_raster.content_reference(),
                                 updated[0].camera, role="reference")
        inputs["ref-v0"] = ViewInput(reference_raster, reference_raster)
        canonical = CanonicalReference("canonical", 1, reference_raster.content_reference(), validated=True,
                                       view_ids=("ref-v0",), validation_evidence=ArtifactReference("canonical-proof", "c"*64, "application/json"))
        revision = replace(revision, views=revision.views+(reference,), canonical_reference=canonical, input_order=())
        region = Region("v0", "important-flag", (.68, .76, .76, .88))
        result = analyze_geometry(revision, inputs, regions=(region,), backend=self.backend())
        native = next(v for v in result.views if v.view_id == "v0")
        self.assertEqual(native.metrics.important_regions[0].status, "unknown")
        pair = next(p for p in result.pair_comparisons if p.target_view_id == "v0")
        self.assertEqual(pair.metrics.important_regions[0].status, "fail")
        self.assertTrue(any(f.code == "geometry.detail_preservation" and f.status == "fail" and region in f.regions
                            and "Direct antipodal" in f.message for f in result.report.findings))
        self.assertTrue(any(f.code == "geometry.attribution" and f.status == "unknown" for f in result.report.findings))
        self.assertTrue(any(f.code == "geometry.reference_conflict" and f.status == "fail" for f in result.report.findings))
        self.assertEqual(GeometryResult.from_json(result.to_json()), result)

    def test_independent_canonical_constraint_is_checked_when_native_views_agree(self):
        revision, inputs = sources()
        pixels = tuple(value for y in range(32) for x in range(32)
                       for value in ((1., 1., 1., 1.) if 10 <= x < 22 and 5 <= y < 27 else (0., 0., 0., 0.)))
        raster = RasterInput.from_pixels(32, 32, pixels, source_bytes=b"independent-narrow-canonical")
        reference = ViewRevision("reference", 1, raster.content_reference(), raster.content_reference(),
                                 revision.views[0].camera, role="reference")
        inputs["reference"] = ViewInput(raster, raster)
        canonical = CanonicalReference("canonical", 1, raster.content_reference(), validated=True,
                                       view_ids=("reference",), validation_evidence=ArtifactReference("canonical-proof", "c"*64, "application/json"))
        revision = replace(revision, views=revision.views+(reference,), canonical_reference=canonical, input_order=())
        result = analyze_geometry(revision, inputs, backend=self.backend())
        self.assertTrue(all(f.status == "pass" for f in result.report.findings if f.code == "geometry.cross_view_conflict"))
        self.assertTrue(any(f.code == "geometry.reference_conflict" and f.status == "fail" for f in result.report.findings))
        self.assertEqual(result.report.verification_status, "fail")

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
