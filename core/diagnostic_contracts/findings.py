"""Measured evidence, explicitly uncertain interpretations and proposed actions."""

from __future__ import annotations

from dataclasses import dataclass

from .codec import JsonContract, require_id, require_text, unique, validate_model
from .enums import (ActionKind, Category, EvidenceKind, JudgmentKind, Severity,
                    ThresholdOperator, VerificationStatus)
from .sources import ArtifactReference, EngineVersion, validate_code


@dataclass(frozen=True)
class Threshold(JsonContract):
    operator: ThresholdOperator
    value: float
    unit: str

    def __post_init__(self) -> None:
        validate_model(self)
        require_text(self.unit, "threshold unit")


@dataclass(frozen=True)
class Measurement(JsonContract):
    name: str
    value: float
    unit: str
    threshold: Threshold | None = None

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.name, "measurement name")
        require_text(self.unit, "measurement unit")
        if self.threshold is not None and self.threshold.unit != self.unit:
            raise ValueError("Measurement and threshold units must agree.")


@dataclass(frozen=True)
class Region(JsonContract):
    """Optional (left, bottom, right, top) bounds in normalized image space."""

    view_id: str
    label: str
    bounds: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.view_id, "region view_id")
        require_text(self.label, "region label")
        if self.bounds is not None:
            left, bottom, right, top = self.bounds
            if not (0 <= left < right <= 1 and 0 <= bottom < top <= 1):
                raise ValueError("Region bounds must have positive area inside [0, 1].")


def validate_targets(view_ids: tuple[str, ...], regions: tuple[Region, ...]) -> None:
    unique(view_ids, "view_ids")
    for view_id in view_ids:
        require_id(view_id, "view_id")
    unique(tuple((r.view_id, r.label, r.bounds) for r in regions), "regions")


@dataclass(frozen=True)
class Evidence(JsonContract):
    evidence_id: str
    kind: EvidenceKind
    description: str
    view_ids: tuple[str, ...] = ()
    regions: tuple[Region, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    artifact: ArtifactReference | None = None

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.evidence_id, "evidence_id")
        require_text(self.description, "evidence description")
        validate_targets(self.view_ids, self.regions)
        unique(tuple(m.name for m in self.measurements), "measurement names")
        if self.kind == EvidenceKind.ARTIFACT and self.artifact is None:
            raise ValueError("Artifact evidence must identify a hashed artifact.")
        if self.kind == EvidenceKind.OBSERVATION and not (self.measurements or self.artifact):
            raise ValueError("An observation requires measurements or a hashed source artifact.")


@dataclass(frozen=True)
class Judgment(JsonContract):
    """Interpretation is separate from observation; confidence is not probability.

    A calibrated confidence additionally identifies its validation evidence.
    A model identifier alone never supplies measured evidence for a finding.
    """

    statement: str
    kind: JudgmentKind
    uncertainty: str
    model: EngineVersion | None = None
    confidence: float | None = None
    confidence_calibrated: bool = False
    calibration_evidence: ArtifactReference | None = None

    def __post_init__(self) -> None:
        validate_model(self)
        require_text(self.statement, "judgment statement")
        require_text(self.uncertainty, "judgment uncertainty")
        if self.kind == JudgmentKind.MODEL and self.model is None:
            raise ValueError("Model judgments must identify their model version.")
        if self.kind == JudgmentKind.INFERENCE and self.model is not None:
            raise ValueError("Model-produced judgments must use kind='model'.")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Judgment confidence must lie inside [0, 1].")
        if self.confidence_calibrated and (self.confidence is None or self.calibration_evidence is None):
            raise ValueError("Calibrated confidence requires a value and validation evidence.")


@dataclass(frozen=True)
class ProposedAction(JsonContract):
    action_id: str
    kind: ActionKind
    description: str
    view_ids: tuple[str, ...] = ()
    regions: tuple[Region, ...] = ()

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.action_id, "action_id")
        require_text(self.description, "action description")
        validate_targets(self.view_ids, self.regions)


@dataclass(frozen=True)
class Finding(JsonContract):
    finding_id: str
    code: str
    category: Category
    severity: Severity
    status: VerificationStatus
    message: str
    view_ids: tuple[str, ...] = ()
    regions: tuple[Region, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    interpretations: tuple[Judgment, ...] = ()
    proposed_actions: tuple[ProposedAction, ...] = ()
    required: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.finding_id, "finding_id")
        validate_code(self.code)
        require_text(self.message, "finding message")
        validate_targets(self.view_ids, self.regions)
        unique(tuple(e.evidence_id for e in self.evidence), "evidence IDs")
        unique(tuple(a.action_id for a in self.proposed_actions), "action IDs")
        if self.status in (VerificationStatus.PASS, VerificationStatus.FAIL) and not self.evidence:
            raise ValueError("Pass/fail findings require supporting evidence.")
        if self.status in (VerificationStatus.UNKNOWN, VerificationStatus.NOT_APPLICABLE):
            require_text(self.reason, "Unknown/not_applicable reason")
