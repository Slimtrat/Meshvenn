"""Registry and stable module-level facade for pipeline implementations."""

from ..pipeline_contracts import ImplementationDescriptor, PipelineContext, PipelineImplementation, PipelineStage
from .helpers import build_default_plan, register_many
from .models import (
    DuplicateImplementationError, InvalidImplementationError, PipelineAvailabilityEntry,
    PipelinePlanValidationIssue, PipelinePlanValidationResult, PipelineRegistryEntry,
    PipelineRegistryError, StageMismatchError, UnknownImplementationError,
)
from .registry import PipelineRegistry

PIPELINE_REGISTRY = PipelineRegistry()


def register_implementation(implementation: PipelineImplementation, *, default: bool = False, replace: bool = False) -> PipelineImplementation:
    return PIPELINE_REGISTRY.register(implementation, default=default, replace=replace)


def unregister_implementation(implementation_id: str) -> PipelineImplementation | None:
    return PIPELINE_REGISTRY.unregister(implementation_id)


def get_implementation(implementation_id: str) -> PipelineImplementation | None:
    return PIPELINE_REGISTRY.get(implementation_id)


def require_implementation(implementation_id: str, *, stage: PipelineStage | None = None) -> PipelineImplementation:
    return PIPELINE_REGISTRY.require(implementation_id, stage=stage)


def implementations_for_stage(stage: PipelineStage) -> tuple[PipelineImplementation, ...]:
    return PIPELINE_REGISTRY.implementations(stage)


def descriptors_for_stage(stage: PipelineStage) -> tuple[ImplementationDescriptor, ...]:
    return PIPELINE_REGISTRY.descriptors(stage)


def availability_for_stage(stage: PipelineStage, context: PipelineContext) -> tuple[PipelineAvailabilityEntry, ...]:
    return PIPELINE_REGISTRY.availability_entries(stage, context)


def default_implementation_id(stage: PipelineStage) -> str | None:
    return PIPELINE_REGISTRY.default_id(stage)


def clear_registry() -> None:
    PIPELINE_REGISTRY.clear()


__all__ = [
    "PipelineRegistryError", "DuplicateImplementationError", "UnknownImplementationError",
    "StageMismatchError", "InvalidImplementationError", "PipelineRegistryEntry",
    "PipelineAvailabilityEntry", "PipelinePlanValidationIssue", "PipelinePlanValidationResult",
    "PipelineRegistry", "build_default_plan", "register_many", "PIPELINE_REGISTRY",
    "register_implementation", "unregister_implementation", "get_implementation",
    "require_implementation", "implementations_for_stage", "descriptors_for_stage",
    "availability_for_stage", "default_implementation_id", "clear_registry",
]
