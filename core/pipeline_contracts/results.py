from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

from ..diagnostic_contracts import DiagnosticReport
from .identifiers import validate_implementation_id
from .stages import PipelineStage


class StageResultState(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class StageExecutionResult:
    stage: PipelineStage
    implementation_id: str
    state: StageResultState
    payload: Any = None
    message: str = ""
    metrics: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    diagnostic_report: DiagnosticReport | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", PipelineStage(self.stage))
        object.__setattr__(self, "implementation_id", validate_implementation_id(self.implementation_id))
        object.__setattr__(self, "state", StageResultState(self.state))
        if self.diagnostic_report is not None and type(self.diagnostic_report) is not DiagnosticReport:
            raise TypeError("diagnostic_report must be a typed DiagnosticReport.")

    def with_diagnostic_report(self, report: DiagnosticReport) -> "StageExecutionResult":
        """Attach evidence without changing technical success or stage payload."""
        return replace(self, diagnostic_report=report)

    def with_diagnostic_report_json(self, content: str) -> "StageExecutionResult":
        return self.with_diagnostic_report(DiagnosticReport.from_json(content))

    def diagnostic_report_json(self) -> str | None:
        return None if self.diagnostic_report is None else self.diagnostic_report.to_json()

    @property
    def success(self) -> bool:
        return self.state == StageResultState.SUCCESS

    @property
    def failed(self) -> bool:
        return self.state == StageResultState.FAILED

    @property
    def skipped(self) -> bool:
        return self.state == StageResultState.SKIPPED

    @classmethod
    def succeeded(cls, *, stage: PipelineStage, implementation_id: str, payload: Any = None, message: str = "", metrics: Mapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, diagnostic_report: DiagnosticReport | None = None) -> "StageExecutionResult":
        return cls(stage, implementation_id, StageResultState.SUCCESS, payload, message, metrics or {}, metadata or {}, diagnostic_report)

    @classmethod
    def skipped_result(cls, *, stage: PipelineStage, implementation_id: str, message: str = "", metadata: Mapping[str, Any] | None = None, diagnostic_report: DiagnosticReport | None = None) -> "StageExecutionResult":
        return cls(stage, implementation_id, StageResultState.SKIPPED, None, message, {}, metadata or {}, diagnostic_report)

    @classmethod
    def failed_result(cls, *, stage: PipelineStage, implementation_id: str, message: str, metadata: Mapping[str, Any] | None = None, diagnostic_report: DiagnosticReport | None = None) -> "StageExecutionResult":
        return cls(stage, implementation_id, StageResultState.FAILED, None, message, {}, metadata or {}, diagnostic_report)
