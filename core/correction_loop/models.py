"""Versioned immutable D6 state; orchestration is not asset certification."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from ..diagnostic_contracts import ArtifactReference,DiagnosticReport,EngineVersion,Measurement,Region,ViewSetRevision
from ..diagnostic_contracts.codec import JsonContract,fingerprint,require_id,require_sha256,require_text,require_version,unique,validate_model
from ..correction_plans import CorrectionPlan,CorrectionPolicy,CorrectionResult,EditAnnotation,PreparedCorrection,ProviderCapabilities


def finite(value,name,low=0,high=1e12):
    if type(value) not in (float,int) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f"{name} must be finite in [{low},{high}].")


def parameters(value):
    if len(value.encode())>65536:
        raise ValueError("Provider parameter record exceeds 64KiB.")
    def pairs(items):
        result={}
        for key,item in items:
            if key in result: raise ValueError("Duplicate provider parameter.")
            result[key]=item
        return result
    parsed=json.loads(value,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError("Nonfinite parameter.")))
    if type(parsed) is not dict: raise ValueError("Provider parameters require a JSON object.")
    fingerprint(parsed)  # finite JSON only


@dataclass(frozen=True)
class LoopBudget(JsonContract):
    max_attempts: int = 3
    max_elapsed_seconds: float = 300.
    max_cost: float = 1.
    cost_unit: str = "USD"
    max_stagnation: int = 2
    request_timeout_seconds: float = 60.
    max_recovery_queries: int = 3

    def __post_init__(self):
        validate_model(self)
        if not 1<=self.max_attempts<=16 or not 1<=self.max_stagnation<=16 or not 0<=self.max_recovery_queries<=16:
            raise ValueError("Loop attempt/recovery bounds exceeded.")
        finite(self.max_elapsed_seconds,"elapsed budget",.001,86400)
        finite(self.request_timeout_seconds,"request timeout",.001,3600)
        finite(self.max_cost,"cost budget",0,1e6)
        require_text(self.cost_unit,"cost unit")


@dataclass(frozen=True)
class AcceptancePolicy(JsonContract):
    objective_name: str = "target_error"
    objective_unit: str = "normalized_error"
    objective_direction: str = "lower"
    min_improvement: float = .01
    required_checks: tuple[str,...] = ("appearance.identity_assessment","quality.export_verified","correction.healthy_constraints","correction.camera_compliance")
    required_engines: tuple[str,...] = ("meshvenn.preflight","meshvenn.geometry_diagnostics","meshvenn.appearance_diagnostics")
    outside_pixel_tolerance: float = 0.
    required_regions: tuple[Region,...] = ()

    def __post_init__(self):
        validate_model(self)
        require_id(self.objective_name,"objective name")
        require_text(self.objective_unit,"objective unit")
        if self.objective_direction not in ("lower","higher"): raise ValueError("Invalid objective direction.")
        finite(self.min_improvement,"minimum improvement",1e-12,1e6)
        finite(self.outside_pixel_tolerance,"protected pixel tolerance",0,1)
        unique(self.required_checks,"required checks")
        unique(self.required_engines,"required engines")
        if len(self.required_regions)>128: raise ValueError("Required region bound exceeded.")


@dataclass(frozen=True)
class SnapshotArtifact(JsonContract):
    role: str
    artifact: ArtifactReference

    def __post_init__(self):
        validate_model(self)
        if self.role not in ("glb","source_state","mesh","diagnostic","other"):
            raise ValueError("Invalid snapshot artifact role.")


@dataclass(frozen=True)
class LoopSnapshot(JsonContract):
    snapshot_id: str
    view_set: ViewSetRevision
    reports: tuple[DiagnosticReport,...]
    metrics: tuple[Measurement,...]
    artifacts: tuple[SnapshotArtifact,...] = ()
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        require_id(self.snapshot_id,"snapshot_id")
        if len(self.view_set.views)>20 or len(self.reports)>20 or len(self.artifacts)>64 or len(self.metrics)>64:
            raise ValueError("Snapshot bounds exceeded.")
        unique(tuple(m.name for m in self.metrics),"snapshot metrics")
        if any(r.view_set.dependency_fingerprint!=self.view_set.dependency_fingerprint for r in self.reports):
            raise ValueError("Snapshot reports belong to a different view revision.")

    @property
    def sha256(self): return fingerprint(self.to_dict())

    @property
    def artifact_hashes(self):
        return tuple(sorted({c.sha256 for v in self.view_set.views for c in (v.image,v.mask) if c}|
                            {a.artifact.sha256 for a in self.artifacts}))


@dataclass(frozen=True)
class ProviderInfo(JsonContract):
    provider_id: str
    model: EngineVersion
    capabilities: ProviderCapabilities
    execution_mode: str = "service_api"
    parameters_json: str = "{}"
    max_cost_per_request: float | None = None
    cost_unit: str = "USD"
    supports_recovery: bool = False
    supports_idempotency: bool = False
    simulation: bool = False

    def __post_init__(self):
        validate_model(self)
        require_id(self.provider_id,"provider_id")
        if self.execution_mode not in ("service_api","host_tool","unavailable"):
            raise ValueError("Generation mode must distinguish host tools from service APIs.")
        if self.max_cost_per_request is not None: finite(self.max_cost_per_request,"request cost ceiling",0,1e6)
        parameters(self.parameters_json)
        require_text(self.cost_unit,"provider cost unit")


@dataclass(frozen=True)
class EvaluatorInfo(JsonContract):
    engine: EngineVersion
    replayable: bool = True
    side_effect_free: bool = True
    simulation: bool = False

    def __post_init__(self):
        validate_model(self)
        if not self.replayable or not self.side_effect_free:
            raise ValueError("Local global evaluation must be replayable without paid side effects.")


@dataclass(frozen=True)
class Usage(JsonContract):
    cost: float | None = None
    cost_unit: str = "USD"
    input_tokens: int | None = None
    output_tokens: int | None = None
    images: int | None = None
    raw_json: str = "{}"

    def __post_init__(self):
        validate_model(self)
        if self.cost is not None: finite(self.cost,"actual cumulative request cost",0,1e9)
        require_text(self.cost_unit,"usage cost unit")
        for value in (self.input_tokens,self.output_tokens,self.images):
            if value is not None and value<0: raise ValueError("Usage counts must be nonnegative.")
        parameters(self.raw_json)


@dataclass(frozen=True)
class GenerationRequest(JsonContract):
    request_id: str
    idempotency_key: str
    session_id: str
    attempt_number: int
    accepted_sha256: str
    plan: CorrectionPlan
    prepared: PreparedCorrection
    provider: ProviderInfo
    max_cost: float
    expires_at: float
    request_sha256: str = ""

    def __post_init__(self):
        validate_model(self)
        require_id(self.request_id,"request_id")
        require_sha256(self.idempotency_key)
        require_sha256(self.accepted_sha256)
        if not 1<=self.attempt_number<=16: raise ValueError("Invalid attempt number.")
        finite(self.max_cost,"reserved request cost",0,1e6)
        finite(self.expires_at,"request expiration")
        if self.plan.plan_id!=self.prepared.plan_id or self.plan.context_sha256!=self.prepared.context_sha256:
            raise ValueError("Prepared package and plan differ.")
        content=self.to_dict()
        content.pop("request_sha256")
        expected=fingerprint(content)
        if self.request_sha256 and self.request_sha256!=expected:
            raise ValueError("Generation request content fingerprint does not match.")
        object.__setattr__(self,"request_sha256",expected)

    @property
    def sha256(self): return self.request_sha256


@dataclass(frozen=True)
class ProviderReceipt(JsonContract):
    request_id: str
    request_sha256: str
    provider_id: str
    model: EngineVersion
    status: str
    usage: Usage
    output_image: ArtifactReference | None = None
    provider_operation_id: str = ""
    parameters_json: str = "{}"
    receipt_evidence: ArtifactReference | None = None
    error: str = ""

    def __post_init__(self):
        validate_model(self)
        require_id(self.request_id,"receipt request_id")
        require_sha256(self.request_sha256)
        if self.status not in ("pending","completed","failed","unknown","not_submitted"):
            raise ValueError("Invalid provider completion state.")
        parameters(self.parameters_json)
        if self.status=="completed" and self.output_image is None:
            raise ValueError("Completed generation requires its actual image artifact.")
        if self.status=="not_submitted" and (self.receipt_evidence is None or self.usage.cost!=0):
            raise ValueError("Conclusive non-submission requires receipt evidence and zero measured cost.")
        if len(self.error)>1024 or len(self.provider_operation_id)>512:
            raise ValueError("Provider receipt text exceeds its bounds.")

    @property
    def sha256(self): return fingerprint(self.to_dict())


@dataclass(frozen=True)
class GlobalEvaluation(JsonContract):
    request_id: str
    request_sha256: str
    candidate: LoopSnapshot
    evaluator: EvaluatorInfo
    checked_view_ids: tuple[str,...]

    def __post_init__(self):
        validate_model(self)
        require_id(self.request_id,"evaluation request_id")
        require_sha256(self.request_sha256)
        unique(self.checked_view_ids,"globally evaluated view IDs")


@dataclass(frozen=True)
class AcceptanceDecision(JsonContract):
    promoted: bool
    reasons: tuple[str,...]
    improvement: float | None
    required_status: str
    before_sha256: str
    candidate_sha256: str

    def __post_init__(self):
        validate_model(self)
        require_sha256(self.before_sha256)
        require_sha256(self.candidate_sha256)
        if self.required_status not in ("pass","fail","unknown"): raise ValueError("Invalid global assessment.")
        if self.promoted and (self.reasons or self.required_status!="pass" or self.improvement is None):
            raise ValueError("Promotion requires supported improvement and no global failure/uncertainty.")


@dataclass(frozen=True)
class LoopAttempt(JsonContract):
    request: GenerationRequest
    status: str = "dispatching"
    receipts: tuple[ProviderReceipt,...] = ()
    evaluation: GlobalEvaluation | None = None
    decision: AcceptanceDecision | None = None
    recovery_queries: int = 0
    error: str = ""
    rejected_receipts: tuple[ProviderReceipt,...] = ()

    def __post_init__(self):
        validate_model(self)
        if self.status not in ("dispatching","awaiting_host","pending","completion_uncertain","candidate_ready","evaluating","accepted","rejected","failed","not_submitted","late"):
            raise ValueError("Invalid attempt stage.")
        if len(self.receipts)+len(self.rejected_receipts)>64 or not 0<=self.recovery_queries<=16: raise ValueError("Attempt audit bounds exceeded.")
        if any(r.request_id!=self.request.request_id or r.request_sha256!=self.request.sha256 for r in (*self.receipts,*self.rejected_receipts)):
            raise ValueError("Receipt belongs to another exact request.")

    @property
    def known_cost(self): return max((r.usage.cost for r in self.receipts if r.usage.cost is not None),default=0.)

    @property
    def cost_uncertain(self):
        terminal=self.terminal_receipt
        receipt=terminal or (self.receipts[-1] if self.receipts else None)
        return receipt is None or receipt.usage.cost is None

    @property
    def completed_receipt(self):
        return next((r for r in reversed(self.receipts) if r.status=="completed"),None)

    @property
    def terminal_receipt(self):
        return next((r for r in reversed(self.receipts) if r.status in ("completed","failed","not_submitted")),None)


@dataclass(frozen=True)
class LoopEvent(JsonContract):
    sequence: int
    at: float
    kind: str
    detail: str
    request_id: str | None = None

    def __post_init__(self):
        validate_model(self)
        if self.sequence<1: raise ValueError("Event sequence must be positive.")
        finite(self.at,"event time")
        require_id(self.kind,"event kind")
        if len(self.detail)>2048: raise ValueError("Event detail exceeds bound.")


@dataclass(frozen=True)
class LoopState(JsonContract):
    session_id: str
    accepted: LoopSnapshot
    plans: CorrectionResult
    budget: LoopBudget
    acceptance_policy: AcceptancePolicy
    provider: ProviderInfo
    evaluator: EvaluatorInfo | None
    annotations: tuple[EditAnnotation,...]
    correction_policy: CorrectionPolicy
    implementation_sha256: str
    started_at: float
    last_at: float
    status: str = "ready"
    attempts: tuple[LoopAttempt,...] = ()
    events: tuple[LoopEvent,...] = ()
    stagnation_count: int = 0
    limitations: tuple[str,...] = ()
    verification_status: str = "unknown"
    schema_version: int = 1
    runtime_sha256: str = ""

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        import re
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}",self.session_id): raise ValueError("Invalid loop session ID.")
        require_sha256(self.implementation_sha256)
        if self.runtime_sha256: require_sha256(self.runtime_sha256)
        finite(self.started_at,"session start")
        finite(self.last_at,"session clock")
        if self.last_at<self.started_at: raise ValueError("Session clock regressed.")
        if self.status not in ("ready","provider_unavailable","needs_input","awaiting_host","pending","completion_uncertain","candidate_ready","evaluating","awaiting_evaluator","stopped","cancelled"):
            raise ValueError("Invalid session stage.")
        if len(self.attempts)>self.budget.max_attempts or len(self.events)>1024 or self.verification_status!="unknown":
            raise ValueError("Loop audit bound or orchestration verification violated.")
        if tuple(e.sequence for e in self.events)!=tuple(range(1,len(self.events)+1)):
            raise ValueError("Loop events must preserve contiguous audit order.")
        if self.plans.view_set.dependency_fingerprint!=self.accepted.view_set.dependency_fingerprint:
            raise ValueError("Current plans do not belong to the accepted snapshot.")

    @property
    def known_cost(self): return sum(a.known_cost for a in self.attempts)

    @property
    def cost_uncertain(self): return any(a.cost_uncertain for a in self.attempts)
