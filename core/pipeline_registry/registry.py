from __future__ import annotations

from typing import Iterator

from ..pipeline_contracts import (
    PIPELINE_STAGE_ORDER, ImplementationAvailability, ImplementationDescriptor,
    PipelineContext, PipelineImplementation, PipelinePlan, PipelineStage,
    PipelineStageSelection, validate_implementation_id,
)
from .models import (
    DuplicateImplementationError, InvalidImplementationError, PipelineAvailabilityEntry,
    PipelinePlanValidationIssue, PipelinePlanValidationResult, PipelineRegistryEntry,
    StageMismatchError, UnknownImplementationError,
)


def _read_descriptor(implementation: PipelineImplementation) -> ImplementationDescriptor:
    if implementation is None:
        raise InvalidImplementationError("Pipeline implementation cannot be None.")
    if not hasattr(implementation, "descriptor"):
        raise InvalidImplementationError("Pipeline implementation must expose a descriptor property.")
    descriptor = getattr(implementation, "descriptor")
    if not isinstance(descriptor, ImplementationDescriptor):
        raise InvalidImplementationError("Pipeline implementation descriptor must be an ImplementationDescriptor.")
    for method in ("availability", "execute"):
        if not callable(getattr(implementation, method, None)):
            raise InvalidImplementationError(f'Implementation "{descriptor.identifier}" must define {method}(context).')
    return descriptor


class PipelineRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, PipelineRegistryEntry] = {}
        self._stage_ids: dict[PipelineStage, list[str]] = {stage: [] for stage in PIPELINE_STAGE_ORDER}
        self._default_ids: dict[PipelineStage, str] = {}
        self._registration_counter = 0

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    def __contains__(self, implementation_id: object) -> bool:
        return isinstance(implementation_id, str) and implementation_id in self._entries

    def __iter__(self) -> Iterator[PipelineImplementation]:
        return (entry.implementation for entry in self.entries())

    def clear(self) -> None:
        self._entries.clear()
        for ids in self._stage_ids.values():
            ids.clear()
        self._default_ids.clear()
        self._registration_counter = 0

    def register(self, implementation: PipelineImplementation, *, default: bool = False, replace: bool = False) -> PipelineImplementation:
        descriptor = _read_descriptor(implementation)
        identifier = descriptor.identifier
        existing = self._entries.get(identifier)
        if existing is not None:
            if not replace:
                raise DuplicateImplementationError(f'Pipeline implementation "{identifier}" is already registered.')
            if existing.descriptor.stage != descriptor.stage:
                raise StageMismatchError(f'Cannot replace implementation "{identifier}" from stage "{existing.descriptor.stage.value}" with implementation from stage "{descriptor.stage.value}".')
            replacement = PipelineRegistryEntry(implementation, descriptor, existing.registration_index, existing.is_default or default)
            self._entries[identifier] = replacement
            if replacement.is_default:
                self.set_default(descriptor.stage, identifier)
            return implementation
        self._entries[identifier] = PipelineRegistryEntry(implementation, descriptor, self._registration_counter)
        self._registration_counter += 1
        self._stage_ids[descriptor.stage].append(identifier)
        if descriptor.stage not in self._default_ids:
            default = True
        if default:
            self.set_default(descriptor.stage, identifier)
        return implementation

    def unregister(self, implementation_id: str) -> PipelineImplementation | None:
        identifier = validate_implementation_id(implementation_id)
        entry = self._entries.pop(identifier, None)
        if entry is None:
            return None
        stage_ids = self._stage_ids[entry.descriptor.stage]
        if identifier in stage_ids:
            stage_ids.remove(identifier)
        if self._default_ids.get(entry.descriptor.stage) == identifier:
            self._default_ids.pop(entry.descriptor.stage, None)
            if stage_ids:
                self.set_default(entry.descriptor.stage, stage_ids[0])
        return entry.implementation

    def set_default(self, stage: PipelineStage, implementation_id: str) -> None:
        stage, identifier = PipelineStage(stage), validate_implementation_id(implementation_id)
        entry = self.require_entry(identifier)
        if entry.descriptor.stage != stage:
            raise StageMismatchError(f'Implementation "{identifier}" belongs to stage "{entry.descriptor.stage.value}", not "{stage.value}".')
        previous_id = self._default_ids.get(stage)
        if previous_id is not None and previous_id in self._entries:
            previous = self._entries[previous_id]
            self._entries[previous_id] = PipelineRegistryEntry(previous.implementation, previous.descriptor, previous.registration_index, False)
        current = self._entries[identifier]
        self._entries[identifier] = PipelineRegistryEntry(current.implementation, current.descriptor, current.registration_index, True)
        self._default_ids[stage] = identifier

    def default_id(self, stage: PipelineStage) -> str | None:
        return self._default_ids.get(PipelineStage(stage))

    def default_entry(self, stage: PipelineStage) -> PipelineRegistryEntry | None:
        identifier = self.default_id(stage)
        return None if identifier is None else self._entries.get(identifier)

    def default(self, stage: PipelineStage) -> PipelineImplementation | None:
        entry = self.default_entry(stage)
        return None if entry is None else entry.implementation

    def get_entry(self, implementation_id: str) -> PipelineRegistryEntry | None:
        return self._entries.get(validate_implementation_id(implementation_id))

    def require_entry(self, implementation_id: str) -> PipelineRegistryEntry:
        entry = self.get_entry(implementation_id)
        if entry is None:
            raise UnknownImplementationError(f'Unknown pipeline implementation: "{implementation_id}".')
        return entry

    def get(self, implementation_id: str) -> PipelineImplementation | None:
        entry = self.get_entry(implementation_id)
        return None if entry is None else entry.implementation

    def require(self, implementation_id: str, *, stage: PipelineStage | None = None) -> PipelineImplementation:
        entry = self.require_entry(implementation_id)
        if stage is not None and entry.descriptor.stage != PipelineStage(stage):
            raise StageMismatchError(f'Implementation "{implementation_id}" belongs to "{entry.descriptor.stage.value}", but "{PipelineStage(stage).value}" was requested.')
        return entry.implementation

    def entries(self, stage: PipelineStage | None = None) -> tuple[PipelineRegistryEntry, ...]:
        if stage is None:
            return tuple(sorted(self._entries.values(), key=lambda item: (PIPELINE_STAGE_ORDER.index(item.descriptor.stage), item.registration_index)))
        return tuple(self._entries[i] for i in self._stage_ids[PipelineStage(stage)] if i in self._entries)

    def implementations(self, stage: PipelineStage | None = None) -> tuple[PipelineImplementation, ...]:
        return tuple(entry.implementation for entry in self.entries(stage))

    def descriptors(self, stage: PipelineStage | None = None) -> tuple[ImplementationDescriptor, ...]:
        return tuple(entry.descriptor for entry in self.entries(stage))

    def implementation_ids(self, stage: PipelineStage | None = None) -> tuple[str, ...]:
        return tuple(descriptor.identifier for descriptor in self.descriptors(stage))

    def has_stage(self, stage: PipelineStage) -> bool:
        return bool(self._stage_ids[PipelineStage(stage)])

    def availability(self, implementation_id: str, context: PipelineContext) -> ImplementationAvailability:
        result = self.require(implementation_id).availability(context)
        if not isinstance(result, ImplementationAvailability):
            raise InvalidImplementationError(f'Implementation "{implementation_id}" availability() must return ImplementationAvailability.')
        return result

    def availability_entries(self, stage: PipelineStage, context: PipelineContext) -> tuple[PipelineAvailabilityEntry, ...]:
        result = []
        for entry in self.entries(PipelineStage(stage)):
            availability = entry.implementation.availability(context)
            if not isinstance(availability, ImplementationAvailability):
                raise InvalidImplementationError(f'Implementation "{entry.descriptor.identifier}" availability() must return ImplementationAvailability.')
            result.append(PipelineAvailabilityEntry(entry.descriptor, availability, entry.is_default))
        return tuple(result)

    def available_entries(self, stage: PipelineStage, context: PipelineContext) -> tuple[PipelineAvailabilityEntry, ...]:
        return tuple(entry for entry in self.availability_entries(stage, context) if entry.available)

    def resolve_selection(self, selection: PipelineStageSelection) -> PipelineImplementation:
        return self.require(selection.implementation_id, stage=selection.stage)

    def resolve_stage(self, stage: PipelineStage, implementation_id: str | None = None) -> PipelineImplementation:
        stage = PipelineStage(stage)
        if implementation_id:
            return self.require(implementation_id, stage=stage)
        implementation = self.default(stage)
        if implementation is None:
            raise UnknownImplementationError(f'No implementation registered for pipeline stage "{stage.value}".')
        return implementation

    def validate_plan(self, plan: PipelinePlan, context: PipelineContext | None = None, *, check_availability: bool = True) -> PipelinePlanValidationResult:
        context, issues = context or PipelineContext(), []
        for selection in plan.enabled_selections:
            entry = self._entries.get(selection.implementation_id)
            if entry is None:
                issues.append(PipelinePlanValidationIssue(selection.stage, selection.implementation_id, "Implementation is not registered."))
                continue
            if entry.descriptor.stage != selection.stage:
                issues.append(PipelinePlanValidationIssue(selection.stage, selection.implementation_id, f'Implementation belongs to "{entry.descriptor.stage.value}" instead of "{selection.stage.value}".'))
                continue
            if not check_availability:
                continue
            try:
                availability = entry.implementation.availability(context)
            except Exception as exc:
                issues.append(PipelinePlanValidationIssue(selection.stage, selection.implementation_id, f"Availability check failed: {exc}"))
                continue
            if not isinstance(availability, ImplementationAvailability):
                issues.append(PipelinePlanValidationIssue(selection.stage, selection.implementation_id, "availability() returned an invalid result."))
            elif not availability.available:
                issues.append(PipelinePlanValidationIssue(selection.stage, selection.implementation_id, availability.reason.strip() or "Implementation is unavailable."))
        return PipelinePlanValidationResult(tuple(issues))
