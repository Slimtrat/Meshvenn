from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

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

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", PipelineStage(self.stage))
        object.__setattr__(self, "implementation_id", validate_implementation_id(self.implementation_id))
        object.__setattr__(self, "state", StageResultState(self.state))

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
    def succeeded(cls, *, stage: PipelineStage, implementation_id: str, payload: Any = None, message: str = "", metrics: Mapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None) -> "StageExecutionResult":
        return cls(stage, implementation_id, StageResultState.SUCCESS, payload, message, metrics or {}, metadata or {})

    @classmethod
    def skipped_result(cls, *, stage: PipelineStage, implementation_id: str, message: str = "", metadata: Mapping[str, Any] | None = None) -> "StageExecutionResult":
        return cls(stage, implementation_id, StageResultState.SKIPPED, None, message, {}, metadata or {})

    @classmethod
    def failed_result(cls, *, stage: PipelineStage, implementation_id: str, message: str, metadata: Mapping[str, Any] | None = None) -> "StageExecutionResult":
        return cls(stage, implementation_id, StageResultState.FAILED, None, message, {}, metadata or {})
