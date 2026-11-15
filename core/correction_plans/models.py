"""Strict proposals and provider request packages, never edit/acceptance results."""
from __future__ import annotations

from dataclasses import dataclass

from ..diagnostic_contracts import (ArtifactReference, CameraDeclaration, DiagnosticReport,
    EngineVersion, Evidence, Judgment, Measurement, Region, ViewRevision, ViewSetRevision)
from ..diagnostic_contracts.codec import (JsonContract, fingerprint, require_id, require_sha256,
                                        require_text, require_version, unique, validate_model)
from ..geometry_diagnostics.models import MaskArtifact
from .policy import CorrectionPolicy

CONTROLS = ("region_edit","mask","multiple_references","camera_request","identity_reference")
ACTIONS = ("edit_region","prepare_alignment","repair_mask","inspect_input","verify_camera",
           "request_view","select_reference","diagnose_engine","review_evidence")


@dataclass(frozen=True)
class ProviderCapabilities(JsonContract):
    provider_id: str = "unspecified"
    version: str = "1"
    controls: tuple[str, ...] = ()
    max_references: int = 8

    def __post_init__(self):
        validate_model(self)
        require_id(self.provider_id,"provider_id")
        require_text(self.version,"capability version")
        unique(self.controls,"provider controls")
        if any(c not in CONTROLS for c in self.controls) or not 1 <= self.max_references <= 20:
            raise ValueError("Unsupported provider control or reference limit.")
        object.__setattr__(self,"controls",tuple(sorted(self.controls)))

    @property
    def dependency_fingerprint(self):
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class EditAnnotation(JsonContract):
    report_sha256: str
    finding_id: str
    region: Region
    provenance: ArtifactReference
    mask: MaskArtifact | None = None
    coordinate_space: str = "source"

    def __post_init__(self):
        validate_model(self)
        require_sha256(self.report_sha256)
        require_id(self.finding_id,"annotation finding_id")
        if self.coordinate_space != "source" or self.region.bounds is None:
            raise ValueError("Edit annotations require explicit original-image bounds.")
        if self.mask is not None:
            if not self.mask.occupied_count:
                raise ValueError("An edit-support mask cannot be empty.")
            left,bottom,right,top = self.region.bounds
            for index,value in enumerate(self.mask.values):
                if value:
                    u = index%self.mask.width/(self.mask.width-1) if self.mask.width>1 else .5
                    v = index//self.mask.width/(self.mask.height-1) if self.mask.height>1 else .5
                    if not left<=u<=right or not bottom<=v<=top:
                        raise ValueError("Edit mask pixels must stay inside the declared original-image region.")


@dataclass(frozen=True)
class PlanEvidence(JsonContract):
    report_sha256: str
    finding_id: str
    code: str
    status: str
    observations: tuple[Evidence, ...]

    def __post_init__(self):
        validate_model(self)
        require_sha256(self.report_sha256)
        require_id(self.finding_id,"finding_id")
        if self.status not in ("pass","fail","unknown","not_applicable"):
            raise ValueError("Invalid evidence status.")


@dataclass(frozen=True)
class PlanInvariant(JsonContract):
    kind: str
    description: str
    view_ids: tuple[str, ...] = ()
    regions: tuple[Region, ...] = ()
    artifact: ArtifactReference | None = None

    def __post_init__(self):
        validate_model(self)
        require_id(self.kind,"invariant kind")
        require_text(self.description,"invariant description")


@dataclass(frozen=True)
class Postcondition(JsonContract):
    kind: str
    description: str
    view_ids: tuple[str, ...] = ()
    regions: tuple[Region, ...] = ()
    code: str = ""
    baseline: tuple[Measurement, ...] = ()

    def __post_init__(self):
        validate_model(self)
        require_id(self.kind,"postcondition kind")
        require_text(self.description,"postcondition description")


@dataclass(frozen=True)
class CameraRequirement(JsonContract):
    view_id: str | None
    camera: CameraDeclaration | None
    description: str
    requested_azimuth_degrees: float | None = None
    requested_elevation_degrees: float | None = None
    compliance_guaranteed: bool = False

    def __post_init__(self):
        validate_model(self)
        require_text(self.description,"camera requirement")
        if self.compliance_guaranteed:
            raise ValueError("A provider's camera-request support is not a compliance guarantee.")
        if self.requested_azimuth_degrees is not None and not 0 <= self.requested_azimuth_degrees < 360:
            raise ValueError("Requested azimuth must be normalized.")
        if self.requested_elevation_degrees is not None and not -90 <= self.requested_elevation_degrees <= 90:
            raise ValueError("Requested elevation is unsupported.")


@dataclass(frozen=True)
class PromptPackage(JsonContract):
    instructions: tuple[str, ...]
    original: ViewRevision | None
    references: tuple[ViewRevision, ...]
    target_region: Region | None
    annotation: EditAnnotation | None
    camera: CameraRequirement | None
    invariants: tuple[PlanInvariant, ...]
    postconditions: tuple[Postcondition, ...]
    evidence: tuple[PlanEvidence, ...]
    coordinate_space: str = "source"
    candidate_origin: str = "derived"
    preserve_originals: bool = True

    def __post_init__(self):
        validate_model(self)
        if self.coordinate_space != "source" or self.candidate_origin != "derived" or not self.preserve_originals:
            raise ValueError("Provider packages preserve original evidence and create derived candidates only.")
        if len(self.instructions)>32 or any(not s or len(s)>2048 for s in self.instructions):
            raise ValueError("Prompt instructions exceed the bounded template profile.")
        if len(self.references)>20:
            raise ValueError("Too many reference snapshots.")


@dataclass(frozen=True)
class CorrectionPlan(JsonContract):
    plan_id: str
    context_sha256: str
    action_kind: str
    readiness: str
    target: Region | None
    evidence: tuple[PlanEvidence, ...]
    probable_cause: Judgment
    expected_improvement: str
    required_controls: tuple[str, ...]
    unsupported_controls: tuple[str, ...]
    limitations: tuple[str, ...]
    alternative: str
    prompt: PromptPackage
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        require_id(self.plan_id,"plan_id")
        require_sha256(self.context_sha256)
        if self.action_kind not in ACTIONS or self.readiness not in ("ready","needs_input","unsupported","blocked"):
            raise ValueError("Unknown correction action/readiness.")
        unique(self.required_controls,"required controls")
        unique(self.unsupported_controls,"unsupported controls")
        if any(c not in CONTROLS for c in self.required_controls) or not set(self.unsupported_controls)<=set(self.required_controls):
            raise ValueError("Invalid provider capability negotiation.")
        if self.readiness=="ready" and (self.unsupported_controls or self.action_kind!="edit_region"):
            raise ValueError("Only a supported targeted edit can be provider-ready.")
        if self.action_kind=="edit_region" and (self.target is None or self.target.bounds is None):
            raise ValueError("Generative edits require a localized original-image target.")
        if self.target != self.prompt.target_region or self.evidence != self.prompt.evidence:
            raise ValueError("Prompt/evidence must match the exact planned target.")
        require_text(self.expected_improvement,"expected improvement")

    @property
    def dependency_fingerprint(self):
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class CorrectionResult(JsonContract):
    view_set: ViewSetRevision
    reports: tuple[DiagnosticReport, ...]
    capabilities: ProviderCapabilities
    annotations: tuple[EditAnnotation, ...]
    policy_sha256: str
    engine: EngineVersion
    source_sha256: str
    context_sha256: str
    plans: tuple[CorrectionPlan, ...]
    completion: str = "complete"
    verification_status: str = "unknown"
    schema_version: int = 1
    limitations: tuple[str, ...] = ()
    policy: CorrectionPolicy | None = None

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        for value in (self.policy_sha256,self.source_sha256,self.context_sha256):
            require_sha256(value)
        if self.policy is not None and self.policy.dependency_fingerprint!=self.policy_sha256:
            raise ValueError("The policy snapshot does not match its correction context.")
        if self.completion not in ("complete","partial","cancelled") or self.verification_status!="unknown":
            raise ValueError("A correction proposal cannot certify the asset or a future edit.")
        unique(tuple(p.plan_id for p in self.plans),"plan IDs")
        if any(p.context_sha256!=self.context_sha256 for p in self.plans):
            raise ValueError("Plans belong to a different correction context.")

    def is_stale(self,view_set,*,context_sha256=None):
        return (self.view_set.dependency_fingerprint!=view_set.dependency_fingerprint or
                context_sha256 is not None and context_sha256!=self.context_sha256)


@dataclass(frozen=True)
class PreparedCorrection(JsonContract):
    plan_id: str
    context_sha256: str
    prompt: PromptPackage
    derived_from: tuple[str, ...]
    postconditions: tuple[Postcondition, ...]
    candidate_origin: str = "derived"
    verification_status: str = "unknown"
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        require_id(self.plan_id,"plan_id")
        require_sha256(self.context_sha256)
        for value in self.derived_from:
            require_sha256(value)
        if not self.derived_from or self.candidate_origin!="derived" or self.verification_status!="unknown":
            raise ValueError("Prepared requests create derived candidates and cannot certify them.")
        if self.postconditions!=self.prompt.postconditions:
            raise ValueError("Postconditions were detached from the prepared prompt.")
