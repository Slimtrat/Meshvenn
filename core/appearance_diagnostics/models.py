"""Replayable appearance evidence in original bottom-left image coordinates."""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..diagnostic_contracts import ArtifactReference, DiagnosticReport, Region
from ..diagnostic_contracts.codec import JsonContract, fingerprint, require_id, require_sha256, validate_model
from ..geometry_diagnostics.models import MaskArtifact
from .policy import AppearanceViewSettings
from .surface import SurfaceMesh
from .semantic_models import SemanticEvaluation


@dataclass(frozen=True)
class AppearanceRegionAnchor(JsonContract):
    """Optional authored 3D support for an expected original-image region.

    An image rectangle alone cannot tell an occluder from the named feature.
    These normalized bounds select the actual expected surface, not foreground
    that happens to project into the same rectangle.
    """
    region: Region
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    provenance: ArtifactReference
    triangle_indices: tuple[int, ...] = ()

    def __post_init__(self):
        validate_model(self)
        if any(not -1 <= lo <= hi <= 1 for lo,hi in zip(self.minimum,self.maximum)):
            raise ValueError("Appearance region anchors use normalized ordered surface bounds.")
        if sum(lo < hi for lo,hi in zip(self.minimum,self.maximum)) < 2:
            raise ValueError("An appearance surface region requires at least two nonzero extents.")
        if len(self.triangle_indices) > 65_536 or len(set(self.triangle_indices)) != len(self.triangle_indices) or any(i < 0 for i in self.triangle_indices):
            raise ValueError("Invalid appearance surface region triangle IDs.")

    def contains(self, position, triangle_index, epsilon=1e-6):
        return (position is not None and triangle_index is not None and
                (not self.triangle_indices or triangle_index in self.triangle_indices) and
                all(lo-epsilon <= value <= hi+epsilon for value,lo,hi in zip(position,self.minimum,self.maximum)))


@dataclass(frozen=True)
class AppearancePixel(JsonContract):
    x: int
    y: int
    target_uv: tuple[float, float] | None
    reference_uv: tuple[float, float] | None
    triangle_index: int | None
    visibility: str
    state: str
    reason: str
    target_raw_rgb: tuple[float, float, float] | None = None
    reference_raw_rgb: tuple[float, float, float] | None = None
    target_rgb: tuple[float, float, float] | None = None
    reference_rgb: tuple[float, float, float] | None = None
    raw_delta: float | None = None
    corrected_delta: float | None = None

    def __post_init__(self):
        validate_model(self)
        if self.x < 0 or self.y < 0 or self.triangle_index is not None and self.triangle_index < 0:
            raise ValueError("Appearance sample indices must be nonnegative.")
        if any(value is not None and value < 0 for value in (self.raw_delta, self.corrected_delta)):
            raise ValueError("Appearance distances must be nonnegative.")


@dataclass(frozen=True)
class AppearancePairResult(JsonContract):
    pair_id: str
    target_view_id: str
    reference_view_id: str
    map_view_id: str
    width: int
    height: int
    pixels: tuple[AppearancePixel, ...]
    expected_mask: MaskArtifact
    visible_mask: MaskArtifact
    comparable_mask: MaskArtifact
    changed_mask: MaskArtifact
    unknown_mask: MaskArtifact
    fitted_neutral_gain: float | None
    fitted_residual: float | None
    reference_eligibility: str

    def __post_init__(self):
        validate_model(self)
        for value in (self.pair_id, self.target_view_id, self.reference_view_id, self.map_view_id):
            require_id(value, "appearance comparison identifier")
        if self.map_view_id not in (self.target_view_id, self.reference_view_id):
            raise ValueError("A comparison raster must name its original source view.")
        if not 1 <= self.width <= 128 or not 1 <= self.height <= 128:
            raise ValueError("Appearance grids are bounded at 128 pixels per axis.")
        if len(self.pixels) > self.width*self.height or len({(p.x,p.y) for p in self.pixels}) != len(self.pixels):
            raise ValueError("A pair has duplicated or excessive raster samples.")
        for sample in self.pixels:
            if not sample.x < self.width or not sample.y < self.height:
                raise ValueError("Appearance sample lies outside its declared grid.")
        for mask in (self.expected_mask, self.visible_mask, self.comparable_mask, self.changed_mask, self.unknown_mask):
            if (mask.width,mask.height) != (self.width,self.height):
                raise ValueError("Appearance masks must agree with the comparison grid.")
        if any(not changed <= comparable <= visible <= expected for expected,visible,comparable,changed in zip(
                self.expected_mask.values,self.visible_mask.values,self.comparable_mask.values,self.changed_mask.values)):
            raise ValueError("Changed appearance samples require comparable visible source support.")
        if any(u != int(e and not c) for e,c,u in zip(self.expected_mask.values,self.comparable_mask.values,self.unknown_mask.values)):
            raise ValueError("Every unresolved expected appearance sample must remain unknown.")

    @property
    def dependency_fingerprint(self):
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class AppearanceRegionResult(JsonContract):
    region: Region
    coverage_status: str
    color_status: str
    expected_samples: int
    visible_samples: int
    comparable_samples: int
    changed_samples: int
    coverage_fraction: float | None
    reason: str
    counterpart_view_ids: tuple[str, ...]

    def __post_init__(self):
        validate_model(self)
        if self.coverage_status not in ("pass","unknown") or self.color_status not in ("pass","fail","unknown"):
            raise ValueError("Invalid appearance regional status.")
        if not 0 <= self.changed_samples <= self.comparable_samples <= self.visible_samples <= self.expected_samples:
            raise ValueError("Appearance regional sample counts disagree.")
        if self.coverage_fraction is not None and not 0 <= self.coverage_fraction <= 1:
            raise ValueError("Appearance regional coverage must lie in [0,1].")
        if self.coverage_fraction != (self.visible_samples/self.expected_samples if self.expected_samples else None):
            raise ValueError("Regional coverage must agree with the measured sample counts.")
        if self.coverage_status == "pass" and not self.visible_samples or self.color_status in ("pass","fail") and not self.comparable_samples:
            raise ValueError("Regional pass/fail requires resolved samples.")


@dataclass(frozen=True)
class AppearanceViewResult(JsonContract):
    view_id: str
    role: str
    width: int
    height: int
    pair_ids: tuple[str, ...]
    expected_mask: MaskArtifact
    visible_mask: MaskArtifact
    comparable_mask: MaskArtifact
    changed_mask: MaskArtifact
    unknown_mask: MaskArtifact
    regions: tuple[AppearanceRegionResult, ...]
    visible_triangles: tuple[int, ...]
    source_sha256: str
    decoded_sha256: str
    settings: AppearanceViewSettings

    def __post_init__(self):
        validate_model(self)
        require_id(self.view_id, "appearance view_id")
        require_sha256(self.source_sha256)
        require_sha256(self.decoded_sha256)
        if not 1 <= self.width <= 128 or not 1 <= self.height <= 128:
            raise ValueError("Appearance view grid is out of bounds.")
        for mask in (self.expected_mask,self.visible_mask,self.comparable_mask,self.changed_mask,self.unknown_mask):
            if (mask.width,mask.height) != (self.width,self.height):
                raise ValueError("Appearance view masks disagree with the source grid.")
        if any(not c <= m <= v <= e or u != int(e and not m) for e,v,m,c,u in zip(
                self.expected_mask.values,self.visible_mask.values,self.comparable_mask.values,self.changed_mask.values,self.unknown_mask.values)):
            raise ValueError("Appearance view mask support/unknown invariants disagree.")
        if any(r.region.view_id != self.view_id for r in self.regions):
            raise ValueError("Appearance view regions must use original coordinates of this view.")


@dataclass(frozen=True)
class AppearanceProvenance(JsonContract):
    source_sha256: str
    context_sha256: str
    surface_sha256: str | None
    image_fingerprints: tuple[tuple[str,str,str], ...]
    upstream_report_sha256: tuple[str, ...]
    settings_fingerprints: tuple[tuple[str,str], ...]
    grid_samples: int
    work_units: int
    sample_budget: int
    work_budget: int
    elapsed_seconds: float
    deadline_seconds: float

    def __post_init__(self):
        validate_model(self)
        for value in (self.source_sha256,self.context_sha256,*self.upstream_report_sha256):
            require_sha256(value)
        if self.surface_sha256 is not None:
            require_sha256(self.surface_sha256)
        if not 0 <= self.grid_samples <= self.sample_budget or not 0 <= self.work_units <= self.work_budget:
            raise ValueError("Appearance execution exceeds its recorded compute bounds.")
        if self.elapsed_seconds < 0 or not 0 < self.deadline_seconds <= 120:
            raise ValueError("Appearance timing is invalid.")


@dataclass(frozen=True)
class AppearanceResult(JsonContract):
    report: DiagnosticReport
    surface: SurfaceMesh | None
    views: tuple[AppearanceViewResult, ...]
    pairs: tuple[AppearancePairResult, ...]
    semantic: SemanticEvaluation | None
    upstream_reports: tuple[DiagnosticReport, ...]
    provenance: AppearanceProvenance
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        if self.schema_version != 1:
            raise ValueError("Unsupported appearance result schema.")
        ids = {view.view_id for view in self.report.view_set.views}
        if len({view.view_id for view in self.views}) != len(self.views) or any(view.view_id not in ids for view in self.views):
            raise ValueError("Appearance results must bind unique views of their exact source revision.")
        if any(p.target_view_id not in ids or p.reference_view_id not in ids for p in self.pairs):
            raise ValueError("Appearance comparisons escape the source view set.")
        if len({p.pair_id for p in self.pairs}) != len(self.pairs):
            raise ValueError("Appearance comparison IDs must be unique.")
        if self.surface is not None and self.surface.sha256 != self.provenance.surface_sha256:
            raise ValueError("Appearance surface does not match recorded provenance.")
        if self.semantic is not None and self.semantic.request is not None:
            if self.semantic.request.view_set != self.report.view_set or self.semantic.request.context_sha256 != self.provenance.context_sha256:
                raise ValueError("Semantic evidence belongs to a different appearance context.")

    @property
    def identity_status(self):
        gates = [f.status.value for f in self.report.findings if f.code == "appearance.identity_assessment"]
        return "fail" if "fail" in gates else "pass" if gates and all(s == "pass" for s in gates) else "unknown"

    @property
    def deterministic_status(self):
        findings = tuple(f for f in self.report.findings if not f.code.startswith("appearance.semantic_")
                         and f.code != "appearance.identity_assessment")
        policy = replace(self.report.policy, required_checks=tuple(
            code for code in self.report.policy.required_checks if code != "appearance.identity_assessment"))
        return replace(self.report, policy=policy, findings=findings).verification_status.value

    def is_stale(self, view_set, *, context_sha256=None, policy=None, engines=None,
                 source_sha256=None, semantic_dependency=None):
        return (self.report.view_set.dependency_fingerprint != view_set.dependency_fingerprint or
                context_sha256 is not None and context_sha256 != self.provenance.context_sha256 or
                policy is not None and policy.contract() != self.report.policy or
                engines is not None and tuple(sorted(engines,key=lambda e:e.engine_id)) != self.report.engines or
                source_sha256 is not None and source_sha256 != self.provenance.source_sha256 or
                semantic_dependency is not None and (self.semantic is None or
                    semantic_dependency != self.semantic.dependency_fingerprint))
