"""Versioned report snapshots and dependency-based invalidation."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .codec import JsonContract, fingerprint, require_id, require_text, require_version, unique, validate_model
from .enums import CompletionState, JudgmentKind, Severity, VerificationStatus
from .findings import Finding
from .sources import DiagnosticPolicy, DiagnosticResolution, EngineVersion, ViewSetRevision


@dataclass(frozen=True)
class DiagnosticReport(JsonContract):
    report_id: str
    view_set: ViewSetRevision
    engines: tuple[EngineVersion, ...]
    policy: DiagnosticPolicy
    resolution: DiagnosticResolution
    findings: tuple[Finding, ...]
    assumptions: tuple[str, ...] = ()
    completion: CompletionState = CompletionState.COMPLETE
    schema_version: int = 1

    def __post_init__(self) -> None:
        validate_model(self)
        require_version(self.schema_version)
        require_id(self.report_id, "report_id")
        unique(tuple(e.engine_id for e in self.engines), "engine IDs")
        unique(tuple(f.finding_id for f in self.findings), "finding IDs")
        unique(self.assumptions, "assumptions")
        for assumption in self.assumptions:
            require_text(assumption, "assumption")
        ids = {view.view_id for view in self.view_set.views}
        engines = set(self.engines)
        for finding in self.findings:
            targets = [finding, *finding.evidence, *finding.proposed_actions]
            for target in targets:
                referenced = set(target.view_ids) | {r.view_id for r in target.regions}
                if not referenced <= ids:
                    raise ValueError("Finding/evidence/action targets must belong to this exact view set.")
            for judgment in finding.interpretations:
                if judgment.kind == JudgmentKind.MODEL and judgment.model not in engines:
                    raise ValueError("Model judgment version must appear in the report engines.")
        object.__setattr__(self, "engines", tuple(sorted(self.engines, key=lambda e: e.engine_id)))
        object.__setattr__(self, "findings", tuple(sorted(self.findings, key=lambda f: f.finding_id)))
        object.__setattr__(self, "assumptions", tuple(sorted(self.assumptions)))

    @property
    def missing_required_checks(self) -> tuple[str, ...]:
        present = {finding.code for finding in self.findings}
        return tuple(code for code in self.policy.required_checks if code not in present)

    @property
    def verification_status(self) -> VerificationStatus:
        """Conservative evidence decision, independent of technical completion.

        A policy names checks even when their engines did not run. Every finding
        for a required code participates: a passing duplicate cannot hide a
        failed or unknown region. Optional judgments cannot overrule these.
        """
        required_codes = set(self.policy.required_checks)
        checks = tuple(f for f in self.findings
                       if f.required or f.code in required_codes or f.severity == Severity.BLOCKING)
        if any(f.status == VerificationStatus.FAIL for f in checks):
            return VerificationStatus.FAIL
        if (self.completion != CompletionState.COMPLETE or self.missing_required_checks
                or not checks or not self.engines
                or any(f.status == VerificationStatus.UNKNOWN for f in checks)):
            return VerificationStatus.UNKNOWN
        if all(f.status == VerificationStatus.NOT_APPLICABLE for f in checks):
            return VerificationStatus.NOT_APPLICABLE
        return VerificationStatus.PASS

    def dependency_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "view_set": self.view_set.dependency_dict(),
            "engines": [engine.to_dict() for engine in self.engines],
            "policy": self.policy.to_dict(),
            "resolution": self.resolution.to_dict(),
            "assumptions": list(self.assumptions),
        }

    @property
    def dependency_fingerprint(self) -> str:
        return fingerprint(self.dependency_dict())

    def is_stale(self, view_set: ViewSetRevision, *, policy: DiagnosticPolicy | None = None,
                 engines: tuple[EngineVersion, ...] | None = None,
                 resolution: DiagnosticResolution | None = None,
                 assumptions: tuple[str, ...] | None = None) -> bool:
        """Compare a new dependency snapshot without rewriting or rerunning results."""
        candidate = replace(self, view_set=view_set, findings=(), policy=policy or self.policy,
                            engines=self.engines if engines is None else engines,
                            resolution=resolution or self.resolution,
                            assumptions=self.assumptions if assumptions is None else assumptions)
        return candidate.dependency_fingerprint != self.dependency_fingerprint

    def require_current(self, view_set: ViewSetRevision, **dependencies) -> None:
        if self.is_stale(view_set, **dependencies):
            raise ValueError("Diagnostic report is stale for the supplied dependencies.")
