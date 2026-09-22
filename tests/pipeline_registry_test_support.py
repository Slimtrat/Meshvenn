from __future__ import annotations
import sys
import unittest
from pathlib import Path
from typing import Any
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from core.pipeline_contracts import AvailabilityState, ImplementationAvailability, ImplementationDescriptor, PipelineContext, PipelinePlan, PipelineStage, PipelineStageSelection, StageExecutionResult
from core.pipeline_registry import DuplicateImplementationError, InvalidImplementationError, PipelineRegistry, PipelineRegistryError, StageMismatchError, UnknownImplementationError, build_default_plan, register_many

class FakeImplementation:

    def __init__(self, *, identifier: str, stage: PipelineStage, label: str | None=None, availability: ImplementationAvailability | None=None, payload: Any=None) -> None:
        self._descriptor = ImplementationDescriptor(identifier=identifier, stage=stage, label=label or identifier, description=f'Fake implementation for {stage.value}')
        self._availability = availability or ImplementationAvailability.ready_state()
        self.payload = payload
        self.availability_calls = 0
        self.execute_calls = 0

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        self.availability_calls += 1
        return self._availability

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        self.execute_calls += 1
        return StageExecutionResult.succeeded(stage=self.descriptor.stage, implementation_id=self.descriptor.identifier, payload=self.payload)

class InvalidAvailabilityImplementation(FakeImplementation):

    def availability(self, context: PipelineContext):
        return 'ready'

class ExplodingAvailabilityImplementation(FakeImplementation):

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        raise RuntimeError('boom')

class MissingAvailabilityImplementation:

    def __init__(self) -> None:
        self.descriptor = ImplementationDescriptor(identifier='missing-availability', stage=PipelineStage.GEOMETRY, label='Missing Availability', description='Invalid test implementation.')

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        return StageExecutionResult.succeeded(stage=PipelineStage.GEOMETRY, implementation_id='missing-availability')

class MissingExecuteImplementation:

    def __init__(self) -> None:
        self.descriptor = ImplementationDescriptor(identifier='missing-execute', stage=PipelineStage.GEOMETRY, label='Missing Execute', description='Invalid test implementation.')

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        return ImplementationAvailability.ready_state()

def geometry_impl(identifier: str='geometry-a', **kwargs) -> FakeImplementation:
    return FakeImplementation(identifier=identifier, stage=PipelineStage.GEOMETRY, **kwargs)

def material_impl(identifier: str='material-a', **kwargs) -> FakeImplementation:
    return FakeImplementation(identifier=identifier, stage=PipelineStage.MATERIAL, **kwargs)

def rig_impl(identifier: str='rig-a', **kwargs) -> FakeImplementation:
    return FakeImplementation(identifier=identifier, stage=PipelineStage.RIG, **kwargs)
