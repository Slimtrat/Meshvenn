"""Stable public contracts for the implementation-agnostic pipeline."""

from .context import PipelineContext
from .identifiers import IMPLEMENTATION_ID_PATTERN, validate_implementation_id
from .implementations import AvailabilityState, ImplementationAvailability, ImplementationDescriptor, PipelineImplementation
from .plan import PipelinePlan, PipelineStageSelection
from .results import StageExecutionResult, StageResultState
from .stages import PIPELINE_STAGE_ORDER, PIPELINE_STAGE_SPEC_BY_STAGE, PIPELINE_STAGE_SPECS, PipelineStage, PipelineStageSpec, stage_spec

__all__ = [
    "IMPLEMENTATION_ID_PATTERN", "validate_implementation_id", "PipelineStage",
    "PipelineStageSpec", "PIPELINE_STAGE_SPECS", "PIPELINE_STAGE_ORDER",
    "PIPELINE_STAGE_SPEC_BY_STAGE", "stage_spec", "ImplementationDescriptor",
    "AvailabilityState", "ImplementationAvailability", "PipelineContext",
    "StageResultState", "StageExecutionResult", "PipelineImplementation",
    "PipelineStageSelection", "PipelinePlan",
]
