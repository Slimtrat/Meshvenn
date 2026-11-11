"""Immutable, strict JSON artifacts for bounded geometry diagnostics."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..diagnostic_contracts import DiagnosticReport, Region
from ..diagnostic_contracts.codec import JsonContract, validate_model, require_sha256
from ..image_mask import BinaryMask
from ..native_bridge import NativeVolume


@dataclass(frozen=True)
class MaskArtifact(JsonContract):
    width: int
    height: int
    values_hex: str
    sha256: str

    def __post_init__(self):
        validate_model(self)
        require_sha256(self.sha256)
        if not 1 <= self.width <= 256 or not 1 <= self.height <= 256:
            raise ValueError("Diagnostic raster dimensions must be in [1,256].")
        if len(self.values_hex) != self.width * self.height * 2:
            raise ValueError("Diagnostic raster encoded length does not match its grid.")
        raw = bytes.fromhex(self.values_hex)
        if len(raw) != self.width * self.height or any(v > 1 for v in raw):
            raise ValueError("Diagnostic masks require exactly one binary byte per pixel.")
        if self.values_hex != raw.hex() or self.sha256 != self.digest(self.width, self.height, raw):
            raise ValueError("Diagnostic mask content hash does not match.")

    @staticmethod
    def digest(width, height, values):
        return hashlib.sha256(f"mask:{width}:{height}:".encode() + values).hexdigest()

    @classmethod
    def from_mask(cls, mask):
        return cls(mask.width, mask.height, mask.values.hex(), cls.digest(mask.width, mask.height, mask.values))

    @property
    def values(self):
        return bytes.fromhex(self.values_hex)

    @property
    def occupied_count(self):
        return sum(self.values)

    def as_mask(self):
        return BinaryMask(self.width, self.height, self.values)


@dataclass(frozen=True)
class VolumeArtifact(JsonContract):
    width: int
    depth: int
    height: int
    values_hex: str
    occupied_count: int
    bounds: tuple[int, int, int, int, int, int] | None
    sha256: str

    def __post_init__(self):
        validate_model(self)
        require_sha256(self.sha256)
        if not (8 <= self.width == self.depth == self.height <= 64):
            raise ValueError("Diagnostic volume must be cubic with side in [8,64].")
        if len(self.values_hex) != self.width ** 3 * 2:
            raise ValueError("Diagnostic volume encoded length does not match its grid.")
        raw = bytes.fromhex(self.values_hex)
        if len(raw) != self.width ** 3 or any(v > 1 for v in raw) or sum(raw) != self.occupied_count:
            raise ValueError("Native volume has invalid occupancy data.")
        if (self.occupied_count == 0) != (self.bounds is None):
            raise ValueError("Native volume bounds and occupancy disagree.")
        if self.bounds is not None:
            if any(not 0 <= lo <= hi < self.width for lo, hi in zip(self.bounds[::2], self.bounds[1::2])):
                raise ValueError("Native volume bounds are outside its grid.")
            occupied = (i for i, value in enumerate(raw) if value)
            first = next(occupied)
            size = self.width
            left = right = first % size
            bottom = top = first // size % size
            low = high = first // (size * size)
            for index in occupied:
                x, y, z = index % size, index // size % size, index // (size * size)
                left, right, bottom, top, low, high = min(left, x), max(right, x), min(bottom, y), max(top, y), min(low, z), max(high, z)
            if self.bounds != (left, right, bottom, top, low, high):
                raise ValueError("Native volume bounds do not match actual occupied voxels.")
        if self.values_hex != raw.hex() or self.sha256 != self.digest(self.width, raw):
            raise ValueError("Native volume artifact hash does not match.")

    @staticmethod
    def digest(resolution, values):
        return hashlib.sha256(f"volume:{resolution}:".encode() + values).hexdigest()

    @classmethod
    def from_native(cls, volume):
        return cls(volume.width, volume.depth, volume.height, volume.values.hex(),
                   volume.occupied_count, volume.bounds, cls.digest(volume.width, volume.values))

    @property
    def values(self):
        return bytes.fromhex(self.values_hex)

    def as_native(self):
        return NativeVolume(self.width, self.depth, self.height, self.values, self.occupied_count, self.bounds)


@dataclass(frozen=True)
class RegionMeasurement(JsonContract):
    region: Region
    status: str
    reason: str
    expected_pixels: int
    missing_pixels: int
    recall: float | None
    beyond_tolerance_pixels: int = 0

    def __post_init__(self):
        validate_model(self)
        if self.status not in ("pass", "fail", "unknown") or (self.recall is not None and not 0 <= self.recall <= 1):
            raise ValueError("Invalid regional measurement.")
        if not 0 <= self.missing_pixels <= self.expected_pixels:
            raise ValueError("Invalid regional missing pixels.")


@dataclass(frozen=True)
class ResidualArtifact(JsonContract):
    pixel_count: int
    bounds: tuple[float, float, float, float]

    def __post_init__(self):
        validate_model(self)
        if self.pixel_count <= 0 or not (0 <= self.bounds[0] < self.bounds[2] <= 1 and
                                         0 <= self.bounds[1] < self.bounds[3] <= 1):
            raise ValueError("Invalid residual region.")


@dataclass(frozen=True)
class GeometryMetrics(JsonContract):
    iou: float
    precision: float
    recall: float
    expected_pixels: int
    actual_pixels: int
    intersection_pixels: int
    missing_pixels: int
    extraneous_pixels: int
    contour_mean_pixels: float | None
    contour_max_pixels: float | None
    missing_mask: MaskArtifact
    extraneous_mask: MaskArtifact
    missing_regions: tuple[ResidualArtifact, ...]
    extraneous_regions: tuple[ResidualArtifact, ...]
    important_regions: tuple[RegionMeasurement, ...]
    components: tuple[RegionMeasurement, ...]
    component_count: int = 0
    components_truncated: bool = False
    missing_beyond_tolerance_pixels: int = 0
    extraneous_beyond_tolerance_pixels: int = 0
    missing_region_count: int = 0
    extraneous_region_count: int = 0

    def __post_init__(self):
        validate_model(self)
        if any(not 0 <= v <= 1 for v in (self.iou, self.precision, self.recall)):
            raise ValueError("Geometry ratios must be in [0,1].")


@dataclass(frozen=True)
class ViewGeometryResult(JsonContract):
    view_id: str
    expected: MaskArtifact
    reprojected: MaskArtifact
    metrics: GeometryMetrics
    resolution_tolerance_pixels: float
    source_width: int
    source_height: int
    source_mask_sha256: str
    decoded_mask_sha256: str
    aligned_mask_sha256: str
    sampling: str = "nearest-endpoint-grid-no-source-mutation"

    def __post_init__(self):
        validate_model(self)


@dataclass(frozen=True)
class SequentialTraceStep(JsonContract):
    view_id: str
    order_index: int
    before: int
    after: int

    def __post_init__(self):
        validate_model(self)
        if not 0 <= self.after <= self.before or self.order_index < 0:
            raise ValueError("Invalid native sequential trace step.")


@dataclass(frozen=True)
class GeometryExperiment(JsonContract):
    experiment_id: str
    excluded_view_ids: tuple[str, ...]
    included_view_ids: tuple[str, ...]
    volume: VolumeArtifact | None
    views: tuple[ViewGeometryResult, ...]
    state: str
    elapsed_seconds: float

    def __post_init__(self):
        validate_model(self)
        if self.state not in ("complete", "empty", "unknown", "native_failure", "time_budget", "cancelled"):
            raise ValueError("Invalid geometry experiment state.")


@dataclass(frozen=True)
class GeometryProvenance(JsonContract):
    backend: str
    library_sha256: str
    source_sha256: str
    python_executable: str
    native_abi: int
    resolution: int
    thread_count: int
    symmetry_x: bool
    requested_experiments: int
    completed_experiments: int
    native_projection_applications: int
    voxel_capacity: int
    raster_pixel_budget: int
    deadline_seconds: float
    elapsed_seconds: float
    native_elapsed_seconds: float
    termination: str
    host_platform: str

    def __post_init__(self):
        validate_model(self)


@dataclass(frozen=True)
class GeometryPairComparison(JsonContract):
    target_view_id: str
    counterpart_view_id: str
    mapping: str
    expected: MaskArtifact
    counterpart: MaskArtifact
    metrics: GeometryMetrics
    raster_tolerance_pixels: float

    def __post_init__(self):
        validate_model(self)


@dataclass(frozen=True)
class GeometryResult(JsonContract):
    report: DiagnosticReport
    volume: VolumeArtifact | None
    views: tuple[ViewGeometryResult, ...]
    experiments: tuple[GeometryExperiment, ...]
    trace: tuple[SequentialTraceStep, ...]
    provenance: GeometryProvenance
    pair_comparisons: tuple[GeometryPairComparison, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        if self.schema_version != 1:
            raise ValueError("Unsupported geometry diagnostic result schema.")
