"""Measured cross-view silhouette consistency, without automatic truth attribution."""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..diagnostic_contracts import (
    ArtifactReference, DiagnosticPolicy, DiagnosticReport, DiagnosticResolution, EngineVersion,
    Evidence, Finding, Judgment, Measurement, ProposedAction, Region, Threshold, ViewSetRevision,
)
from ..diagnostics_preflight import PreflightPolicy, ViewInput, analyze_preflight
from ..diagnostics_preflight.registration import mask_from_input, resample_mask
from ..native_bridge import NativeProjection
from ..projection_math import direction_to_camera
from .backend import NativeBatch, NativeGeometryBackend, host_platform
from .metrics import compare_masks
from .models import (
    GeometryAttempt, GeometryExperiment, GeometryMetrics, GeometryPairComparison, GeometryProvenance, GeometryResult, MaskArtifact,
    RegionMeasurement, ResidualArtifact, ViewGeometryResult,
)
from .projection import aligned_mask, check_budget, projection_tolerance_pixels, reproject_volume

ENGINE = EngineVersion("meshvenn.geometry_diagnostics", "1.0.0")


@dataclass(frozen=True)
class GeometryPolicy:
    resolution: int = 32
    max_seconds: float = 30.0
    reprojection_size: int = 256
    min_iou: float = 0.90
    max_missing_fraction: float = 0.10
    max_component_missing_fraction: float = 0.25
    max_contour_distance_pixels: float = 3.0
    max_views: int = 10
    max_experiments: int = 12
    max_regions: int = 128
    thread_count: int = 1
    max_projection_work: int = 8_000_000
    pair_raster_tolerance_pixels: float = 0.5
    adaptive_refinement: bool = True
    refinement_resolution: int = 64
    max_total_experiments: int = 24
    max_total_native_applications: int = 220
    max_total_native_voxel_tests: int = 57_671_680
    max_total_python_work: int = 8_000_000_000

    def __post_init__(self):
        for name, low, high in (("resolution", 8, 64), ("reprojection_size", 16, 256),
                                ("max_views", 1, 10), ("max_experiments", 1, 12),
                                ("max_regions", 1, 128), ("thread_count", 1, 8),
                                ("max_projection_work", 1000, 32_000_000), ("refinement_resolution", 8, 64),
                                ("max_total_experiments", 1, 24), ("max_total_native_applications", 1, 220),
                                ("max_total_native_voxel_tests", 512, 57_671_680),
                                ("max_total_python_work", 1000, 8_000_000_000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low},{high}].")
        if type(self.adaptive_refinement) is not bool:
            raise ValueError("adaptive_refinement must be a boolean.")
        for name in ("min_iou", "max_missing_fraction", "max_component_missing_fraction"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be finite in (0,1].")
        if type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 120:
            raise ValueError("max_seconds must be finite in (0,120].")
        if type(self.max_contour_distance_pixels) not in (int, float) or not math.isfinite(self.max_contour_distance_pixels) or not 0 <= self.max_contour_distance_pixels <= 256:
            raise ValueError("Contour threshold must be finite in [0,256] pixels.")
        if (type(self.pair_raster_tolerance_pixels) not in (int, float) or not math.isfinite(self.pair_raster_tolerance_pixels)
                or not 0.5 <= self.pair_raster_tolerance_pixels <= 4):
            raise ValueError("Direct pair tolerance must be finite in [0.5,4] measurement pixels.")

    def contract(self):
        digest = hashlib.sha256(json.dumps(asdict(self), sort_keys=True, allow_nan=False).encode()).hexdigest()
        return DiagnosticPolicy("meshvenn.geometry_diagnostics", "1.0.0", digest,
                                ("geometry.cross_view_conflict", "geometry.detail_preservation",
                                 "coverage.insufficient", "engine.computation"))


def _source_hash():
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parents[1]
    paths = [*Path(__file__).parent.glob("*.py"), root / "projection_alignment.py",
             root / "projection_frame.py", * (root / "projection_math").glob("*.py"),
             *(root / "native_bridge").glob("*.py"), *(root / "diagnostic_contracts").rglob("*.py"),
             *(root / "diagnostics_preflight").rglob("*.py"), root / "image_mask.py", root / "native_loader.py"]
    if (root / "__init__.py").is_file():
        paths.append(root / "__init__.py")
    for path in sorted(paths, key=lambda p: str(p.relative_to(root))):
        logical_path = str(path.relative_to(root)).replace("\\", "/").encode()
        content = path.read_bytes()
        digest.update(len(logical_path).to_bytes(4, "big") + logical_path)
        digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def _mask_digest(mask):
    return MaskArtifact.digest(mask.width, mask.height, mask.values)


def _metric_snapshot(value, view_id):
    def region(item):
        return RegionMeasurement(replace(item.region, view_id=view_id), item.status.value, item.reason,
                                 item.expected_pixels, item.missing_pixels, item.recall,
                                 item.beyond_tolerance_pixels, item.sampled_coverage_status.value,
                                 item.sampled_coverage_reason, item.actual_component_count, item.matched_actual_component)
    return GeometryMetrics(value.iou, value.precision, value.recall, value.expected_pixels,
                           value.actual_pixels, value.intersection_pixels, value.missing_pixels,
                           value.extraneous_pixels, value.contour_mean_pixels, value.contour_max_pixels,
                           MaskArtifact.from_mask(value.missing_mask), MaskArtifact.from_mask(value.extraneous_mask),
                           tuple(ResidualArtifact(r.pixel_count, r.bounds) for r in value.missing_regions),
                           tuple(ResidualArtifact(r.pixel_count, r.bounds) for r in value.extraneous_regions),
                           tuple(region(r) for r in value.important_regions), tuple(region(r) for r in value.components),
                           value.component_count, value.components_truncated,
                           value.missing_beyond_tolerance_pixels, value.extraneous_beyond_tolerance_pixels,
                           value.missing_region_count, value.extraneous_region_count,
                           value.actual_component_count, value.component_correspondence)


def _source_reduction_loss(source, sampled, *, deadline, cancel, max_regions, work_budget=None):
    """Inspect original components before reduction; lost details cannot pass."""
    if (source.width, source.height) == (sampled.width, sampled.height):
        return False, 0
    if work_budget is not None:
        work_budget.reserve_python(8*len(source.values) + len(sampled.values))
    selected = set()
    for y in range(sampled.height):
        sy = int((y / (sampled.height - 1) if sampled.height > 1 else 0.5) * (source.height - 1) + 0.5)
        for x in range(sampled.width):
            sx = int((x / (sampled.width - 1) if sampled.width > 1 else 0.5) * (source.width - 1) + 0.5)
            selected.add(sy * source.width + sx)
    seen = bytearray(len(source.values))
    count, lost = 0, False
    width, total = source.width, len(source.values)
    for start, value in enumerate(source.values):
        if start % 4096 == 0:
            check_budget(deadline=deadline, cancel=cancel)
        if not value or seen[start]:
            continue
        count += 1
        if count > max_regions:
            return True, count
        pending, retained, visited = [start], False, 0
        seen[start] = 1
        while pending:
            index = pending.pop()
            retained |= index in selected
            visited += 1
            if visited % 4096 == 0:
                check_budget(deadline=deadline, cancel=cancel)
            x = index % width
            for neighbor in (index - width, index + width,
                             index - 1 if x else -1, index + 1 if x + 1 < width else -1):
                if 0 <= neighbor < total and source.values[neighbor] and not seen[neighbor]:
                    seen[neighbor] = 1
                    pending.append(neighbor)
        lost |= not retained
    return lost, count


def _independent_reference(view_set, reference, target):
    canonical = view_set.canonical_reference
    if (canonical is None or not canonical.validated or canonical.validation_evidence is None or
            reference.view_id not in canonical.view_ids or reference.role != "reference"):
        return False
    parents = {}
    for view in view_set.views:
        for content in (view.image, view.mask):
            if content:
                parents.setdefault(content.sha256, set()).update(view.derived_from)

    def lineage(view):
        pending = [r.sha256 for r in (view.image, view.mask) if r] + list(view.derived_from)
        found = set()
        while pending:
            value = pending.pop()
            if value not in found:
                found.add(value)
                pending.extend(parents.get(value, ()))
        return found
    # A shared ancestor, including identical original bytes, cannot arbitrate
    # its own descendant. A validated flag does not remove this dependency.
    return not (lineage(reference) & lineage(target))


class _WorkBudget:
    """Shared conservative call capacities, not a CPU instruction counter."""
    def __init__(self, policy):
        self.policy = policy
        self.sessions = self.applications = self.native_voxels = self.python_work = 0

    def reserve_python(self, units):
        if self.python_work + units > self.policy.max_total_python_work:
            raise ValueError("Aggregate Python diagnostic work budget exhausted.")
        self.python_work += units

    def can_reserve_native(self, sessions, applications, resolution):
        return (self.sessions + sessions <= self.policy.max_total_experiments and
                self.applications + applications <= self.policy.max_total_native_applications and
                self.native_voxels + applications*resolution**3 <= self.policy.max_total_native_voxel_tests)

    def reserve_native(self, sessions, applications, resolution):
        if not self.can_reserve_native(sessions, applications, resolution):
            raise ValueError("Aggregate native session/application/voxel work budget exhausted.")
        self.sessions += sessions
        self.applications += applications
        self.native_voxels += applications*resolution**3


def _analyze_geometry_once(view_set: ViewSetRevision, inputs: Mapping[str, ViewInput], *,
                     policy: GeometryPolicy | None = None, backend: NativeGeometryBackend | None = None,
                     regions: Sequence[Region] = (), cancel: Callable[[], bool] | None = None,
                     request_policy: GeometryPolicy, deadline: float, work_budget: _WorkBudget) -> GeometryResult:
    """Read-only, bounded orthographic diagnostic using actual native visual hulls.

    Original masks drive reconstruction. Aligned, explicitly sampled grids drive
    the raster measurements; unresolved parts yield required UNKNOWN findings.
    A leave-one-out residual establishes an incompatibility, never the culprit.
    """
    started = time.monotonic()
    policy, backend = policy or GeometryPolicy(), backend or NativeGeometryBackend()
    counters_before = (work_budget.sessions, work_budget.applications, work_budget.native_voxels, work_budget.python_work)
    views = {v.view_id: v for v in view_set.views}
    inputs, regions = dict(inputs), tuple(regions)
    if any(r.view_id not in views for r in regions):
        raise ValueError("Important regions must belong to the exact input revision.")
    if len(regions) > policy.max_regions:
        raise ValueError("Important region count exceeds the explicit policy budget.")
    findings, assumptions, measured, experiments, trace, pairs, conflicts = [], [], [], [], (), [], []
    full_volume, batch = None, NativeBatch((), "not_started", "", "", "", 0., "not_started")
    native_masks, metric_masks, reduction_unknown, measurement_cache = {}, {}, {}, {}
    completion = "complete"
    source_hash = _source_hash()

    def _compare_masks(*args, **kwargs):
        work_budget.reserve_python(policy.max_projection_work)
        return compare_masks(*args, **kwargs)

    def finding(code, category, status, message, ids=(), *, measurements=(), artifact=None,
                regions=(), key="", required=True, action="inspect_input", interpretation="", severity="error"):
        ids, regions = tuple(ids), tuple(regions)
        token = hashlib.sha256(f"{code}:{','.join(ids)}:{key}".encode()).hexdigest()[:20]
        evidence = (Evidence("e-" + token, "artifact" if artifact else "observation", message, ids, regions,
                             tuple(measurements) or (() if artifact else (Measurement("available_measurements", 0, "count"),)),
                             artifact),)
        findings.append(Finding("g-" + token, code, category, "info" if status == "pass" else severity,
                                status, message, ids, regions, evidence,
                                () if not interpretation else (Judgment(interpretation, "inference",
                                    "Silhouettes and declared cameras cannot establish hidden shape, anatomy, or semantic identity."),),
                                () if status == "pass" else (ProposedAction("a-" + token, action, message, ids, regions),),
                                required, message if status in ("unknown", "not_applicable") else ""))

    assumptions.extend(("Only static orthographic silhouette consistency is measured; hidden concavities, topology, anatomy, appearance and export are not certified.",
                        "Verified camera declarations are producer assumptions backed by existing hashed evidence, not calibration performed by this engine.",
                        "No symmetry, image deletion, regeneration, camera estimation or source replacement is performed.",
                        "Full and leave-one-out geometry use sorted stable view IDs; acquisition-order trace is execution provenance only.",
                        "Native DLL calls have an OS-enforced subprocess deadline; Python preparation and raster work use bounded loops and cooperative deadline/cancellation checks.",
                        f"source_sha256:{source_hash}",
                        "settings:" + json.dumps(asdict(request_policy), sort_keys=True, allow_nan=False, separators=(",", ":")),
                        f"requested_resolution:{request_policy.resolution};attempt_resolution:{policy.resolution}",
                        "measurement_sampling:nearest-endpoint-grid; native reconstruction uses complete original aligned masks"))
    eligible = []
    try:
        check_budget(deadline=deadline, cancel=cancel)
        if len(view_set.views) > 20:
            raise ValueError("At most 20 total observation/reference/control views fit the diagnostic profile.")
        source_pixels = sum(min(1_048_576, max(0, r.width*r.height)) for view_id, data in inputs.items() if view_id in views
                            for r in (data.image, data.mask) if r is not None and type(r.width) is int and type(r.height) is int)
        work_budget.reserve_python(64*source_pixels)
        preflight = analyze_preflight(view_set, inputs, policy=PreflightPolicy(required_cameras=()))
        assumptions.extend(preflight.report.assumptions)
        for item in preflight.report.findings:
            if item.category in ("input", "camera"):
                findings.append(item)
            elif item.category == "alignment":
                findings.append(replace(item, required=False))
        rejected = {view_id for f in preflight.report.findings
                    if f.category in ("input", "camera") and f.status != "pass" and f.required
                    and f.code != "input.subject_truncated" for view_id in f.view_ids}
        eligible = [v.view_id for v in view_set.views if v.role == "observation" and v.view_id not in rejected]
        eligible = [v for v in eligible if v in inputs and views[v].camera.verified]
        if len(eligible) > policy.max_views:
            raise ValueError("Usable observation count exceeds the native diagnostic view budget.")
        order = tuple(v for v in view_set.input_order if v in eligible)
        requested = 1 + (len(eligible) if len(eligible) > 1 else 0) + (int(tuple(eligible) != order) if eligible else 0)
        if requested > policy.max_experiments:
            raise ValueError("Leave-one-out/session count exceeds the declared experiment budget.")
        for view_id in eligible:
            check_budget(deadline=deadline, cancel=cancel)
            work_budget.reserve_python(8*inputs[view_id].image.width*inputs[view_id].image.height)
            native = aligned_mask(mask_from_input(inputs[view_id], 0.1, 0.5), views[view_id].alignment)
            native_masks[view_id] = native
            ratio = min(1., policy.reprojection_size / max(native.width, native.height))
            sampled = resample_mask(native, max(1, round(native.width * ratio)), max(1, round(native.height * ratio)))
            metric_masks[view_id] = sampled
            lost, count = _source_reduction_loss(native, sampled, deadline=deadline, cancel=cancel,
                                                  max_regions=policy.max_regions, work_budget=work_budget)
            reduction_unknown[view_id] = lost
            assumptions.append(f"aligned:{view_id}:{native.width}x{native.height}:{_mask_digest(native)};measurement:{sampled.width}x{sampled.height}:{_mask_digest(sampled)}")
            if lost:
                finding("geometry.resolution_insufficient", "geometry", "unknown",
                        "Measurement reduction loses an original component or exceeds the component budget; retain this detail as unresolved.",
                        (view_id,), measurements=(Measurement("original_component_count", count, "component"),), action="inspect_input")
        directions = [direction_to_camera(azimuth_degrees=views[v].camera.azimuth_degrees,
                                          elevation_degrees=views[v].camera.elevation_degrees) for v in eligible]
        axes = any(abs(sum(a * b for a, b in zip(first, second))) < math.cos(math.radians(15))
                   for i, first in enumerate(directions) for second in directions[i + 1:])
        covered = len(eligible) >= 2 and axes
        finding("coverage.insufficient", "coverage", "pass" if covered else "unknown",
                "At least two nonparallel verified observation axes constrain the visual hull." if covered else
                "Provide at least two nonparallel verified observation axes before full 3D silhouette qualification.",
                measurements=(Measurement("usable_observations", len(eligible), "view"),
                              Measurement("nonparallel_axes_present", int(axes), "boolean")), action="provide_view")
        # Exactly antipodal supported camera declarations constrain the same
        # opaque silhouette with a horizontal reflection (before Flip X). This
        # is an independent raster observation, not a claim about coarse voxels.
        for target_id in eligible:
            for counterpart_id in eligible:
                if counterpart_id == target_id:
                    continue
                target_camera, counterpart_camera = views[target_id].camera, views[counterpart_id].camera
                angular_difference = (counterpart_camera.azimuth_degrees-target_camera.azimuth_degrees) % 360
                if (abs(angular_difference-180) > 1e-7 or
                        abs(counterpart_camera.elevation_degrees+target_camera.elevation_degrees) > 1e-7):
                    continue
                target_source, other_source = native_masks[target_id], native_masks[counterpart_id]
                if (target_source.width, target_source.height) != (other_source.width, other_source.height):
                    finding("geometry.pair_resolution", "geometry", "unknown",
                            "Antipodal observations use different original grids; exact raster correspondence is unresolved in this profile.",
                            (target_id, counterpart_id), key=counterpart_id)
                    continue
                expected, counterpart = metric_masks[target_id], metric_masks[counterpart_id]
                reflected = target_camera.flip_x == counterpart_camera.flip_x
                if reflected:
                    counterpart = counterpart.flipped_x()
                comparison = _compare_masks(expected, counterpart,
                    regions=tuple(r for r in regions if r.view_id == target_id),
                    min_region_recall=1-policy.max_component_missing_fraction, min_region_extent_pixels=1.,
                    resolution_tolerance_pixels=policy.pair_raster_tolerance_pixels, max_regions=policy.max_regions,
                    deadline=deadline, cancel=cancel, max_work=policy.max_projection_work)
                snapshot = _metric_snapshot(comparison, target_id)
                pairs.append(GeometryPairComparison(target_id, counterpart_id,
                    "antipodal-horizontal-reflection" if reflected else "antipodal-flip-x-cancelled",
                    MaskArtifact.from_mask(expected), MaskArtifact.from_mask(counterpart), snapshot, policy.pair_raster_tolerance_pixels))
                outside = snapshot.missing_beyond_tolerance_pixels + snapshot.extraneous_beyond_tolerance_pixels
                bad = outside > 0 and (snapshot.iou < policy.min_iou or 1-snapshot.recall > policy.max_missing_fraction or
                    1-snapshot.precision > policy.max_missing_fraction or
                    (snapshot.contour_max_pixels is not None and snapshot.contour_max_pixels > policy.max_contour_distance_pixels+policy.pair_raster_tolerance_pixels))
                unknown = reduction_unknown[target_id] or reduction_unknown[counterpart_id] or snapshot.components_truncated
                if bad:
                    conflicts.extend(v for v in (target_id, counterpart_id) if v not in conflicts)
                finding("geometry.cross_view_conflict", "geometry", "fail" if bad else "unknown" if unknown else "pass",
                        "Exact antipodal camera correspondence reveals a silhouette conflict; this does not identify which observation is true." if bad else
                        "Antipodal raster correspondence remains unresolved after source reduction." if unknown else
                        "Antipodal raster silhouettes agree within the explicit pixel tolerance.",
                        (target_id, counterpart_id), key="pair-"+counterpart_id,
                        measurements=(Measurement("antipodal_iou", snapshot.iou, "ratio", Threshold(">=", policy.min_iou, "ratio")),
                                      Measurement("pair_raster_tolerance", policy.pair_raster_tolerance_pixels, "pixel")),
                        artifact=ArtifactReference("pair-residual-"+target_id+"-"+counterpart_id,
                                                   snapshot.missing_mask.sha256, "application/x-meshvenn-binary-mask"))
                for index, detail in enumerate(snapshot.important_regions + snapshot.components):
                    finding("geometry.detail_preservation", "geometry", detail.status,
                            "Direct antipodal raster evidence: " + detail.reason,
                            (target_id, counterpart_id), key=f"pair-{counterpart_id}-detail-{index}", regions=(detail.region,),
                            measurements=(Measurement("region_expected_pixels", detail.expected_pixels, "pixel"),
                                          Measurement("region_missing_pixels", detail.missing_pixels, "pixel"),
                                          Measurement("beyond_raster_tolerance", detail.beyond_tolerance_pixels, "pixel")))
                    if detail.status == "fail":
                        conflicts.extend(v for v in (target_id, counterpart_id) if v not in conflicts)
        if not eligible:
            finding("engine.computation", "engine", "not_applicable", "No usable observation can be reconstructed.")
        else:
            projections = [(v, NativeProjection(native_masks[v], views[v].camera.azimuth_degrees,
                                                views[v].camera.elevation_degrees, views[v].camera.flip_x)) for v in eligible]
            applications = len(eligible)**2 + (len(eligible) if tuple(eligible) != order else 0)
            work_budget.reserve_native(requested, applications, policy.resolution)
            batch = backend.run(projections, resolution=policy.resolution, input_order=order,
                                timeout=deadline - time.monotonic(), thread_count=policy.thread_count, cancel=cancel)
            if batch.library_sha256:
                assumptions.append("native_library_sha256:" + batch.library_sha256)
            if batch.python_executable:
                assumptions.append("native_python_host:" + batch.python_executable)
            native_full = next((e for e in batch.experiments if e.experiment_id == "full"), None)
            source_trace = next((e for e in batch.experiments if e.experiment_id == "source-order"), native_full)
            trace = source_trace.trace if source_trace else ()
            full_volume = native_full.volume if native_full else None
            if native_full and source_trace and native_full.volume.sha256 != source_trace.volume.sha256:
                finding("engine.order_instability", "engine", "fail", "Native canonical and acquisition orders produced different final volumes.",
                        measurements=(Measurement("volume_hashes_differ", 1, "boolean"),), action="diagnose_engine")
            if batch.state != "complete":
                code = {"time_budget": "engine.time_budget", "cancelled": "engine.cancelled",
                        "native_failure": "engine.native_failure", "native_unavailable": "engine.native_unavailable",
                        "host_unavailable": "engine.host_unavailable"}.get(batch.state, "engine.worker_failure")
                finding(code, "engine", "unknown", batch.error or f"Native execution ended in state {batch.state}.",
                        measurements=(Measurement("completed_sessions", len(batch.experiments), "experiment"),), action="diagnose_engine")
                completion = "cancelled" if batch.state == "cancelled" else "partial" if batch.state == "time_budget" else "failed"

            def measure(volume, view_id):
                check_budget(deadline=deadline, cancel=cancel)
                cache_key = (volume.sha256, view_id)
                if cache_key in measurement_cache:
                    return measurement_cache[cache_key]
                expected, view = metric_masks[view_id], views[view_id]
                native = volume.as_native()
                tolerance = projection_tolerance_pixels(native, view.camera, expected.width, expected.height)
                work_budget.reserve_python(policy.max_projection_work)
                actual = reproject_volume(native, view.camera, width=expected.width, height=expected.height,
                                          max_work=policy.max_projection_work, deadline=deadline, cancel=cancel)
                comparison = _compare_masks(expected, actual, regions=tuple(r for r in regions if r.view_id == view_id),
                                           min_region_recall=1-policy.max_component_missing_fraction,
                                           resolution_tolerance_pixels=tolerance, max_regions=policy.max_regions,
                                           deadline=deadline, cancel=cancel, max_work=policy.max_projection_work)
                source = inputs[view_id].mask or inputs[view_id].image
                result = ViewGeometryResult(view_id, MaskArtifact.from_mask(expected), MaskArtifact.from_mask(actual),
                                          _metric_snapshot(comparison, view_id), tolerance,
                                          source.width, source.height, source.source_sha256, source.decoded_sha256,
                                          _mask_digest(native_masks[view_id]))
                measurement_cache[cache_key] = result
                return result

            for item in batch.experiments:
                if item.experiment_id == "source-order":
                    continue
                experiment_views = []
                try:
                    for view_id in eligible:
                        experiment_views.append(measure(item.volume, view_id))
                except (TimeoutError, InterruptedError, ValueError):
                    experiments.append(GeometryExperiment(item.experiment_id, tuple(v for v in eligible if v not in item.included_view_ids),
                                       item.included_view_ids, item.volume, tuple(experiment_views), "unknown", item.elapsed_seconds))
                    raise
                experiments.append(GeometryExperiment(item.experiment_id, tuple(v for v in eligible if v not in item.included_view_ids),
                                   item.included_view_ids, item.volume, tuple(experiment_views),
                                   "empty" if not item.volume.occupied_count else "complete", item.elapsed_seconds))
                if item.experiment_id == "full":
                    measured = list(experiment_views)
            finding("engine.computation", "engine", "pass" if batch.state == "complete" else "unknown",
                    "Native canonical/leave-one-out sessions and raster comparisons completed." if batch.state == "complete" else
                    "Native diagnostic computation did not complete every requested session.",
                    measurements=(Measurement("completed_sessions", len(batch.experiments), "experiment"),), action="diagnose_engine")
            if full_volume and full_volume.occupied_count == 0:
                finding("geometry.empty", "geometry", "fail", "The finite native grid contains no occupied voxels and cannot supply usable geometry; this is distinct from a DLL failure.",
                        tuple(eligible), measurements=(Measurement("occupied_voxels", 0, "voxel", Threshold(">", 0, "voxel")),))
                finding("geometry.empty_cause", "geometry", "unknown", "An empty finite grid can arise from underresolved thin geometry or incompatible constraints; emptiness alone does not establish the cause or a culprit.", tuple(eligible))
            for item in measured:
                metric = item.metrics
                outside = metric.missing_beyond_tolerance_pixels + metric.extraneous_beyond_tolerance_pixels
                within_uncertainty = (outside == 0 and metric.expected_pixels > 0 and metric.actual_pixels > 0 and
                                      metric.component_correspondence and not metric.components_truncated)
                contour_bad = metric.contour_max_pixels is not None and metric.contour_max_pixels > policy.max_contour_distance_pixels + item.resolution_tolerance_pixels
                bad = outside > 0 and (metric.iou < policy.min_iou or 1-metric.recall > policy.max_missing_fraction or contour_bad)
                residual = metric.missing_pixels + metric.extraneous_pixels
                if full_volume and not full_volume.occupied_count:
                    bad = False
                    status = "unknown"
                else:
                    status = "fail" if bad else "pass" if within_uncertainty else "unknown" if (
                        not metric.component_correspondence or residual and metric.iou < policy.min_iou) else "pass"
                if bad:
                    conflicts.append(item.view_id)
                finding("geometry.cross_view_conflict", "geometry", status,
                        "Cross-view silhouette mismatch exceeds the declared raster/voxel tolerance." if bad else
                        "Silhouette mismatch cannot be resolved at this diagnostic resolution." if status == "unknown" else
                        "Nonempty silhouettes and one-to-one components agree within the derived raster/voxel uncertainty; raw IoU is retained independently." if within_uncertainty else
                        "Reprojection agrees with this source silhouette within the explicit diagnostic thresholds.",
                        (item.view_id,), measurements=(Measurement("mask_iou", metric.iou, "ratio"),
                                                       Measurement("missing_pixels", metric.missing_pixels, "pixel"),
                                                       Measurement("missing_beyond_tolerance", metric.missing_beyond_tolerance_pixels, "pixel"),
                                                       Measurement("extraneous_beyond_tolerance", metric.extraneous_beyond_tolerance_pixels, "pixel"),
                                                       Measurement("component_correspondence", int(metric.component_correspondence), "boolean"),
                                                       Measurement("derived_resolution_tolerance", item.resolution_tolerance_pixels, "pixel")),
                        artifact=ArtifactReference("residual-"+item.view_id, metric.missing_mask.sha256, "application/x-meshvenn-binary-mask"))
                details = tuple(metric.important_regions) + tuple(metric.components)
                if not details or metric.components_truncated or reduction_unknown.get(item.view_id):
                    finding("geometry.detail_preservation", "geometry", "unknown", "Component/important-region detail is unresolved or exceeds the declared measurement budget.",
                            (item.view_id,), key="unresolved", measurements=(Measurement("measured_components", len(metric.components), "component"),))
                for index, detail in enumerate(details):
                    finding("geometry.detail_preservation", "geometry", detail.status,
                            detail.reason or "Component/important-region coverage was measured independently of mean IoU.",
                            (item.view_id,), key=f"detail-{index}", regions=(detail.region,),
                            measurements=(() if detail.recall is None else (Measurement("region_recall", detail.recall, "ratio", Threshold(">=", 1-policy.max_component_missing_fraction, "ratio")),)) +
                                         (Measurement("region_expected_pixels", detail.expected_pixels, "pixel"),
                                          Measurement("region_missing_pixels", detail.missing_pixels, "pixel")))
                    if index >= len(metric.important_regions):
                        finding("geometry.sampled_component_coverage", "geometry", detail.sampled_coverage_status,
                                detail.sampled_coverage_reason, (item.view_id,), key=f"sampled-{index}",
                                regions=(detail.region,), required=False,
                                measurements=(Measurement("expected_samples", detail.expected_pixels, "pixel"),
                                              Measurement("missing_samples", detail.missing_pixels, "pixel"),
                                              Measurement("overlapping_actual_components", detail.actual_component_count, "component"),
                                              Measurement("isolated_actual_component", int(detail.matched_actual_component is not None), "boolean")))
                    if detail.status == "fail" and full_volume and full_volume.occupied_count and item.view_id not in conflicts:
                        conflicts.append(item.view_id)
            if conflicts:
                finding("geometry.attribution", "geometry", "unknown",
                        "The measured views form a suspect constraint group. Exclusion experiments and the sequential emptying/last view do not identify which source is true.",
                        tuple(eligible), required=False, action="review_reference",
                        measurements=(Measurement("leave_one_out_experiments", sum(e.experiment_id.startswith("without-") for e in experiments), "experiment"),),
                        interpretation="A useful valid view can remove substantial volume; residuals alone cannot justify deleting, regenerating or blaming a view.")
            # Canonical evidence arbitrates only same-camera observations and only
            # after source validity and complete independent lineage validation.
            for target_id in eligible:
                target = views[target_id]
                for reference in view_set.views:
                    if (reference.view_id in rejected or reference.view_id not in inputs or
                            (reference.camera.projection, reference.camera.azimuth_degrees, reference.camera.elevation_degrees, reference.camera.flip_x) !=
                            (target.camera.projection, target.camera.azimuth_degrees, target.camera.elevation_degrees, target.camera.flip_x) or
                            not _independent_reference(view_set, reference, target)):
                        continue
                    reference_original = aligned_mask(mask_from_input(inputs[reference.view_id], .1, .5), reference.alignment)
                    expected = metric_masks[target_id]
                    reference_mask = resample_mask(reference_original, expected.width, expected.height)
                    reference_lost, _ = _source_reduction_loss(reference_original, reference_mask, deadline=deadline,
                                                              cancel=cancel, max_regions=policy.max_regions, work_budget=work_budget)
                    metric = _compare_masks(reference_mask, expected,
                                           resolution_tolerance_pixels=0., max_regions=policy.max_regions,
                                           deadline=deadline, cancel=cancel, max_work=policy.max_projection_work)
                    reverse = _compare_masks(expected, reference_mask,
                                            regions=tuple(r for r in regions if r.view_id == target_id),
                                            min_region_recall=1-policy.max_component_missing_fraction,
                                            resolution_tolerance_pixels=0., max_regions=policy.max_regions,
                                            deadline=deadline, cancel=cancel, max_work=policy.max_projection_work)
                    reverse_snapshot = _metric_snapshot(reverse, target_id)
                    pairs.append(GeometryPairComparison(target_id, reference.view_id, "independent-canonical-same-camera",
                        MaskArtifact.from_mask(expected), MaskArtifact.from_mask(reference_mask), reverse_snapshot, 0.))
                    bad = (metric.iou < policy.min_iou or 1-metric.recall > policy.max_missing_fraction or
                           1-metric.precision > policy.max_missing_fraction or
                           (metric.contour_max_pixels is not None and metric.contour_max_pixels > policy.max_contour_distance_pixels) or
                           any(r.status == "fail" for r in metric.components) or
                           any(r.status == "fail" for r in reverse.components + reverse.important_regions))
                    unresolved = (reference_lost or reduction_unknown.get(target_id) or metric.components_truncated or
                                  reverse.components_truncated or any(r.status == "unknown" for r in metric.components) or
                                  any(r.status == "unknown" for r in reverse.components + reverse.important_regions))
                    finding("geometry.reference_conflict", "geometry", "fail" if bad else "unknown" if unresolved else "pass",
                            "This observation disagrees with independent validated same-camera canonical evidence." if bad else
                            "Independent validated same-camera canonical evidence supports this observation's silhouette.",
                            (target_id, reference.view_id), key=reference.view_id,
                            measurements=(Measurement("canonical_mask_iou", metric.iou, "ratio", Threshold(">=", policy.min_iou, "ratio")),
                                          Measurement("canonical_precision", metric.precision, "ratio"),
                                          Measurement("canonical_recall", metric.recall, "ratio")) +
                                         (() if metric.contour_max_pixels is None else (Measurement("canonical_contour_max", metric.contour_max_pixels, "pixel", Threshold("<=", policy.max_contour_distance_pixels, "pixel")),)),
                            action="review_reference")
                    for index, detail in enumerate(reverse_snapshot.important_regions + reverse_snapshot.components):
                        finding("geometry.detail_preservation", "geometry", detail.status,
                                "Independent canonical raster evidence: " + detail.reason,
                                (target_id, reference.view_id), key=f"canonical-{reference.view_id}-detail-{index}", regions=(detail.region,),
                                measurements=(Measurement("region_expected_pixels", detail.expected_pixels, "pixel"),
                                              Measurement("region_missing_pixels", detail.missing_pixels, "pixel")))
    except InterruptedError:
        completion = "cancelled"
        finding("engine.cancelled", "engine", "unknown", "Geometry diagnostics were cancelled; completed native artifacts are preserved.", action="diagnose_engine")
    except TimeoutError:
        completion = "partial"
        finding("engine.time_budget", "engine", "unknown", "The explicit diagnostic time budget ended during bounded preparation/raster measurement; completed artifacts are preserved.", action="diagnose_engine")
    except ValueError as exc:
        completion = "partial"
        finding("engine.compute_limit", "engine", "unknown", str(exc), action="diagnose_engine")
    present = {f.code for f in findings}
    for code, category in (("geometry.cross_view_conflict", "geometry"), ("geometry.detail_preservation", "geometry"),
                           ("engine.computation", "engine"), ("coverage.insufficient", "coverage")):
        if code not in present:
            finding(code, category, "unknown", "This required diagnostic measurement is unavailable or unfinished.")
    experiment_payload = json.dumps(dict(native_experiments=[e.to_dict() for e in experiments],
                                         antipodal_pairs=[p.to_dict() for p in pairs]), sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    trace_payload = json.dumps([step.to_dict() for step in trace], sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    elapsed = time.monotonic()-started
    finding("engine.provenance", "engine", "pass", "Execution provenance records bounded compute, native binary/source/settings, elapsed time and experiment artifacts; this is not asset acceptance.",
            measurements=(Measurement("total_elapsed_seconds", elapsed, "second"),
                          Measurement("native_worker_elapsed_seconds", batch.elapsed_seconds, "second"),
                          Measurement("completed_native_sessions", len(batch.experiments), "experiment"),
                          Measurement("native_projection_applications", sum(len(e.included_view_ids) for e in batch.experiments), "count"),
                          Measurement("maximum_voxels_per_session", policy.resolution ** 3, "voxel"),
                          Measurement("measurement_pixel_capacity", policy.reprojection_size ** 2, "pixel")),
            artifact=ArtifactReference("geometry-experiments", hashlib.sha256(experiment_payload).hexdigest(), "application/json"), required=False)
    if trace:
        finding("engine.sequential_trace", "engine", "pass", "Acquisition-order occupancy reductions are retained only as execution provenance, never a fault ranking.",
                artifact=ArtifactReference("geometry-source-order-trace", hashlib.sha256(trace_payload).hexdigest(), "application/json"), required=False)
    if batch.library_sha256:
        engines = (ENGINE, EngineVersion("meshvenn.native_core", "abi1-sha256-" + batch.library_sha256))
    else:
        engines = (ENGINE,)
    resolution = DiagnosticResolution(policy.resolution, policy.resolution, policy.resolution, "voxel")
    assumptions = tuple(sorted(set(assumptions)))
    report = DiagnosticReport("geometry-" + view_set.dependency_fingerprint[:20], view_set, engines,
                              request_policy.contract(), resolution, tuple(findings), assumptions, completion)
    report = replace(report, report_id="geometry-" + report.dependency_fingerprint[:20])
    requested = 0 if not eligible else 1 + (len(eligible) if len(eligible) > 1 else 0) + int(tuple(v for v in view_set.input_order if v in eligible) != tuple(eligible))
    provenance = GeometryProvenance("isolated-native-core", batch.library_sha256, source_hash, batch.python_executable,
                                   1, policy.resolution, policy.thread_count, False, requested, len(batch.experiments),
                                   sum(len(e.included_view_ids) for e in batch.experiments), policy.resolution ** 3,
                                   policy.reprojection_size ** 2, request_policy.max_seconds, elapsed,
                                   batch.elapsed_seconds, batch.termination, host_platform(),
                                   request_policy.resolution, (policy.resolution,),
                                   work_budget.sessions-counters_before[0], request_policy.max_total_experiments,
                                   work_budget.applications-counters_before[1], request_policy.max_total_native_applications,
                                   work_budget.native_voxels-counters_before[2], request_policy.max_total_native_voxel_tests,
                                   work_budget.python_work-counters_before[3], request_policy.max_total_python_work)
    return GeometryResult(report, full_volume, tuple(measured), tuple(experiments), trace, provenance, tuple(pairs),
                          request_policy.resolution, policy.resolution)


def analyze_geometry(view_set: ViewSetRevision, inputs: Mapping[str, ViewInput], *,
                     policy: GeometryPolicy | None = None, backend: NativeGeometryBackend | None = None,
                     regions: Sequence[Region] = (), cancel: Callable[[], bool] | None = None) -> GeometryResult:
    """Analyze once, then optionally refine once under the same deadline/budget.

    Reports retain the original request policy. Attempt artifacts keep coarse
    empty geometry and unresolved details even when a finer grid resolves them.
    This function never recurses and never runs more than two resolutions.
    """
    started = time.monotonic()
    policy, backend = policy or GeometryPolicy(), backend or NativeGeometryBackend()
    deadline = started + policy.max_seconds
    work_budget = _WorkBudget(policy)
    inputs, regions = dict(inputs), tuple(regions)
    initial = _analyze_geometry_once(view_set, inputs, policy=policy, backend=backend, regions=regions,
                                     cancel=cancel, request_policy=policy, deadline=deadline, work_budget=work_budget)

    def preserve(result, trigger):
        return GeometryAttempt(result.actual_resolution, trigger, result.report, result.volume, result.views,
                               result.experiments, result.trace, result.provenance, result.pair_comparisons)

    attempts = [preserve(initial, "requested_resolution")]
    result = initial
    empty = initial.volume is not None and initial.volume.occupied_count == 0
    detail_unknown = any(f.code == "geometry.detail_preservation" and f.status == "unknown" and len(f.view_ids) == 1
                         for f in initial.report.findings)
    independent_failure = (any(f.code == "geometry.reference_conflict" and f.status == "fail" for f in initial.report.findings) or
                           any(p.metrics.missing_beyond_tolerance_pixels+p.metrics.extraneous_beyond_tolerance_pixels > 0 and
                               (any(r.status == "fail" for r in p.metrics.important_regions+p.metrics.components) or
                                any(f.code == "geometry.cross_view_conflict" and f.status == "fail" and
                                    f.view_ids == (p.target_view_id, p.counterpart_view_id) for f in initial.report.findings))
                               for p in initial.pair_comparisons))
    invalid_input = any(f.category in ("input", "camera") and f.status == "fail" and f.required for f in initial.report.findings)
    needs_refinement = empty or detail_unknown
    eligible = (policy.adaptive_refinement and needs_refinement and initial.report.completion == "complete" and
                not independent_failure and not invalid_input and policy.refinement_resolution > policy.resolution)
    refinement_reason = "initial_empty" if empty else "native_detail_resolution" if detail_unknown else "not_needed"
    skipped_budget = ""
    if eligible:
        observation_count = len(initial.views)
        if not observation_count and initial.experiments:
            observation_count = len(initial.experiments[0].included_view_ids)
        # Reserve enough capacity for either source order. This conservative gate
        # cannot make input permutation change whether refinement is permitted.
        planned_sessions = 1 if observation_count == 1 else observation_count+2
        planned_applications = 1 if observation_count == 1 else observation_count**2+observation_count
        if cancel is not None and cancel():
            skipped_budget = "cancelled"
        elif time.monotonic() >= deadline:
            skipped_budget = "shared_deadline"
        elif not work_budget.can_reserve_native(planned_sessions, planned_applications, policy.refinement_resolution):
            skipped_budget = "aggregate_native_budget"
        elif work_budget.python_work + policy.max_projection_work > policy.max_total_python_work:
            skipped_budget = "aggregate_python_budget"
        else:
            refined_policy = replace(policy, resolution=policy.refinement_resolution)
            result = _analyze_geometry_once(view_set, inputs, policy=refined_policy, backend=backend, regions=regions,
                                            cancel=cancel, request_policy=policy, deadline=deadline, work_budget=work_budget)
            attempts.append(preserve(result, refinement_reason))

    attempt_manifest = [dict(resolution=a.resolution, trigger=a.trigger,
                             report_sha256=hashlib.sha256(a.report.to_json().encode()).hexdigest(),
                             volume_sha256=a.volume.sha256 if a.volume else None) for a in attempts]
    artifact = ArtifactReference("geometry-resolution-attempts", hashlib.sha256(json.dumps(attempt_manifest,
        sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest(), "application/json")
    measurements = (Measurement("requested_resolution", policy.resolution, "voxel"),
                    Measurement("actual_resolution", result.actual_resolution, "voxel"),
                    Measurement("attempt_count", len(attempts), "attempt"),
                    Measurement("native_sessions_reserved", work_budget.sessions, "experiment", Threshold("<=", policy.max_total_experiments, "experiment")),
                    Measurement("native_applications_reserved", work_budget.applications, "count", Threshold("<=", policy.max_total_native_applications, "count")),
                    Measurement("native_voxel_test_capacity", work_budget.native_voxels, "voxel_test", Threshold("<=", policy.max_total_native_voxel_tests, "voxel_test")),
                    Measurement("python_work_reserved", work_budget.python_work, "declared_work_unit", Threshold("<=", policy.max_total_python_work, "declared_work_unit")),
                    Measurement("shared_deadline_seconds", policy.max_seconds, "second"))
    refinement_incomplete = len(attempts) == 2 and result.report.completion != "complete"
    refinement_status = "unknown" if skipped_budget or refinement_incomplete else "pass" if len(attempts) == 2 else "not_applicable"
    message = ("Refinement could not run within the shared " + skipped_budget + "." if skipped_budget else
               "The bounded refinement was attempted but did not complete; the original coarse attempt remains archived." if refinement_incomplete else
               "One bounded refinement completed; the original coarse attempt remains archived." if len(attempts) == 2 else
               "No additional resolution attempt was required or permitted by the declared refinement profile.")
    refinement = Finding("geometry-refinement", "engine.refinement", "engine", "warning" if skipped_budget else "info",
                         refinement_status, message, evidence=(Evidence("geometry-refinement-execution", "execution", message,
                         measurements=measurements, artifact=artifact),), required=bool(skipped_budget or refinement_incomplete),
                         reason=message if refinement_status in ("unknown", "not_applicable") else "")
    findings = result.report.findings
    completion = result.report.completion
    if skipped_budget:
        completion = "cancelled" if skipped_budget == "cancelled" else "partial"
        if empty and not independent_failure:
            findings = tuple(replace(f, status="unknown", reason="The initial finite grid is empty and the declared refinement could not be completed.")
                             if f.status == "fail" and f.code in ("geometry.empty", "geometry.detail_preservation") else f for f in findings)
    assumptions = tuple(sorted(set(result.report.assumptions + (
        "attempt_resolutions:" + ",".join(str(a.resolution) for a in attempts),
        "At most two attempts share one absolute deadline and aggregate native/Python work budgets; preserved initial outcomes are not overwritten.",))))
    report = replace(result.report, findings=findings+(refinement,), assumptions=assumptions, completion=completion)
    report = replace(report, report_id="geometry-"+report.dependency_fingerprint[:20])
    provenance = replace(result.provenance, requested_resolution=policy.resolution,
                         attempted_resolutions=tuple(a.resolution for a in attempts),
                         requested_experiments=sum(a.provenance.requested_experiments for a in attempts),
                         completed_experiments=sum(a.provenance.completed_experiments for a in attempts),
                         native_projection_applications=sum(a.provenance.native_projection_applications for a in attempts),
                         native_sessions_reserved=work_budget.sessions, native_applications_reserved=work_budget.applications,
                         native_voxel_test_capacity=work_budget.native_voxels, python_work_reserved=work_budget.python_work,
                         elapsed_seconds=time.monotonic()-started,
                         native_elapsed_seconds=sum(a.provenance.native_elapsed_seconds for a in attempts))
    return replace(result, report=report, provenance=provenance, requested_resolution=policy.resolution,
                   actual_resolution=result.actual_resolution, attempts=tuple(attempts))
