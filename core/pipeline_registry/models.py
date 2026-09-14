from __future__ import annotations

from dataclasses import dataclass

from ..pipeline_contracts import ImplementationAvailability, ImplementationDescriptor, PipelineImplementation, PipelineStage


class PipelineRegistryError(RuntimeError):
    pass


class DuplicateImplementationError(PipelineRegistryError):
    pass


class UnknownImplementationError(PipelineRegistryError):
    pass


class StageMismatchError(PipelineRegistryError):
    pass


class InvalidImplementationError(PipelineRegistryError):
    pass


@dataclass(frozen=True)
class PipelineRegistryEntry:
    implementation: PipelineImplementation
    descriptor: ImplementationDescriptor
    registration_index: int
    is_default: bool = False


@dataclass(frozen=True)
class PipelineAvailabilityEntry:
    descriptor: ImplementationDescriptor
    availability: ImplementationAvailability
    is_default: bool = False

    @property
    def identifier(self) -> str:
        return self.descriptor.identifier

    @property
    def stage(self) -> PipelineStage:
        return self.descriptor.stage

    @property
    def available(self) -> bool:
        return self.availability.available


@dataclass(frozen=True)
class PipelinePlanValidationIssue:
    stage: PipelineStage
    implementation_id: str
    message: str


@dataclass(frozen=True)
class PipelinePlanValidationResult:
    issues: tuple[PipelinePlanValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def raise_for_errors(self) -> None:
        if self.valid:
            return
        messages = [f"{issue.stage.value}: {issue.implementation_id}: {issue.message}" for issue in self.issues]
        raise PipelineRegistryError("Pipeline plan is invalid:\n" + "\n".join(f"- {message}" for message in messages))
