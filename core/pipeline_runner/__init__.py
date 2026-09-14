"""Execution engine and reports for pipeline plans."""

from ..pipeline_contracts import PipelineContext, PipelinePlan
from ..pipeline_registry import PipelineRegistry
from .models import (
    PipelineExecutionError, PipelineExecutionReport, PipelineRunIssue,
    PipelineRunnerError, PipelineRunOptions, StageRunRecord,
)
from .results import failed_result as _failed_result
from .results import result_for_exception as _result_for_exception
from .results import skipped_result as _skipped_result
from .runner import PipelineRunner


def run_pipeline(registry: PipelineRegistry, plan: PipelinePlan, context: PipelineContext | None = None, *, options: PipelineRunOptions | None = None) -> PipelineExecutionReport:
    return PipelineRunner(registry).run(plan, context, options=options)


__all__ = [
    "PipelineRunnerError", "PipelineExecutionError", "PipelineRunIssue",
    "StageRunRecord", "PipelineExecutionReport", "PipelineRunOptions",
    "PipelineRunner", "run_pipeline",
]
