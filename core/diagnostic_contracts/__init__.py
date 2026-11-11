"""Shared, Blender-independent diagnostic JSON contracts (schema version 1)."""

from .codec import canonical_json, content_sha256, fingerprint
from .enums import (ActionKind, CameraProjection, Category, CompletionState,
                    EvidenceKind, JudgmentKind, Severity, ThresholdOperator,
                    VerificationStatus, ViewOrigin, ViewRole)
from .findings import Evidence, Finding, Judgment, Measurement, ProposedAction, Region, Threshold
from .reports import DiagnosticReport
from .sources import (ArtifactReference, CameraDeclaration, CanonicalReference,
                      ContentReference, DiagnosticPolicy, DiagnosticResolution,
                      EngineVersion, ViewRevision, ViewSetRevision)

__all__ = (
    "ActionKind", "ArtifactReference", "CameraDeclaration", "CameraProjection",
    "CanonicalReference", "Category", "CompletionState", "ContentReference",
    "DiagnosticPolicy", "DiagnosticReport", "DiagnosticResolution", "EngineVersion",
    "Evidence", "EvidenceKind", "Finding", "Judgment", "JudgmentKind", "Measurement",
    "ProposedAction", "Region", "Severity", "Threshold", "ThresholdOperator",
    "VerificationStatus", "ViewOrigin", "ViewRevision", "ViewRole", "ViewSetRevision",
    "canonical_json", "content_sha256", "fingerprint",
)
