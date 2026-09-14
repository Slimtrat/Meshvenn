from __future__ import annotations

from typing import Any

from ..pipeline_contracts import PipelineStageSelection, StageExecutionResult


def result_for_exception(selection: PipelineStageSelection, exc: Exception) -> StageExecutionResult:
    return StageExecutionResult.failed_result(
        stage=selection.stage,
        implementation_id=selection.implementation_id,
        message=str(exc) or exc.__class__.__name__,
        metadata={"exception_type": exc.__class__.__name__},
    )


def failed_result(selection: PipelineStageSelection, message: str, *, metadata: dict[str, Any] | None = None) -> StageExecutionResult:
    return StageExecutionResult.failed_result(
        stage=selection.stage, implementation_id=selection.implementation_id,
        message=message, metadata=metadata or {},
    )


def skipped_result(selection: PipelineStageSelection, message: str) -> StageExecutionResult:
    return StageExecutionResult.skipped_result(
        stage=selection.stage, implementation_id=selection.implementation_id, message=message,
    )
