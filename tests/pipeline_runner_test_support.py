from __future__ import annotations
import sys
import unittest
from pathlib import Path
from typing import Any
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from core.pipeline_contracts import AvailabilityState, ImplementationAvailability, ImplementationDescriptor, PipelineContext, PipelinePlan, PipelineStage, PipelineStageSelection, StageExecutionResult, StageResultState
from core.pipeline_registry import PipelineRegistry
from core.pipeline_runner import PipelineExecutionError, PipelineExecutionReport, PipelineRunIssue, PipelineRunOptions, PipelineRunner, StageRunRecord, run_pipeline

class FakeImplementation:

    def __init__(self, *, identifier: str, stage: PipelineStage, payload: Any=None, availability: ImplementationAvailability | None=None, result_state: StageResultState=StageResultState.SUCCESS, message: str='', metrics: dict[str, Any] | None=None, metadata: dict[str, Any] | None=None) -> None:
        self._descriptor = ImplementationDescriptor(identifier=identifier, stage=stage, label=identifier, description=f'Fake {stage.value} implementation')
        self.payload = payload
        self._availability = availability or ImplementationAvailability.ready_state()
        self.result_state = result_state
        self.message = message
        self.metrics = metrics or {}
        self.metadata = metadata or {}
        self.availability_calls = 0
        self.execute_calls = 0
        self.received_contexts: list[PipelineContext] = []

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        self.availability_calls += 1
        self.received_contexts.append(context)
        return self._availability

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        self.execute_calls += 1
        self.received_contexts.append(context)
        if self.result_state == StageResultState.SUCCESS:
            return StageExecutionResult.succeeded(stage=self.descriptor.stage, implementation_id=self.descriptor.identifier, payload=self.payload, message=self.message, metrics=self.metrics, metadata=self.metadata)
        if self.result_state == StageResultState.SKIPPED:
            return StageExecutionResult.skipped_result(stage=self.descriptor.stage, implementation_id=self.descriptor.identifier, message=self.message, metadata=self.metadata)
        return StageExecutionResult.failed_result(stage=self.descriptor.stage, implementation_id=self.descriptor.identifier, message=self.message or 'Fake failure.', metadata=self.metadata)

class ExplodingImplementation(FakeImplementation):

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        self.execute_calls += 1
        raise RuntimeError('execution exploded')

class ExplodingAvailabilityImplementation(FakeImplementation):

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        self.availability_calls += 1
        raise RuntimeError('availability exploded')

class InvalidAvailabilityImplementation(FakeImplementation):

    def availability(self, context: PipelineContext):
        self.availability_calls += 1
        return 'ready'

class InvalidResultImplementation(FakeImplementation):

    def execute(self, context: PipelineContext):
        self.execute_calls += 1
        return 'success'

class WrongStageResultImplementation(FakeImplementation):

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        self.execute_calls += 1
        return StageExecutionResult.succeeded(stage=PipelineStage.RIG, implementation_id=self.descriptor.identifier)

class WrongIdResultImplementation(FakeImplementation):

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        self.execute_calls += 1
        return StageExecutionResult.succeeded(stage=self.descriptor.stage, implementation_id='another-implementation')

class InputImplementation(FakeImplementation):

    def __init__(self, *, payload: Any='input-data') -> None:
        super().__init__(identifier='projection-images', stage=PipelineStage.INPUT, payload=payload)

class GeometryImplementation(FakeImplementation):

    def __init__(self, *, payload: Any='geometry-data') -> None:
        super().__init__(identifier='native-hull', stage=PipelineStage.GEOMETRY, payload=payload)

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        self.availability_calls += 1
        if not context.has_output(PipelineStage.INPUT):
            return ImplementationAvailability.unavailable('Input missing.')
        return ImplementationAvailability.ready_state()

class MaterialImplementation(FakeImplementation):

    def __init__(self, *, payload: Any='material-data') -> None:
        super().__init__(identifier='projected-color-v1.2', stage=PipelineStage.MATERIAL, payload=payload)

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        self.availability_calls += 1
        if not context.has_output(PipelineStage.GEOMETRY):
            return ImplementationAvailability.unavailable('Geometry missing.')
        return ImplementationAvailability.ready_state()

class RigImplementation(FakeImplementation):

    def __init__(self, *, payload: Any='rig-data') -> None:
        super().__init__(identifier='auto-rig', stage=PipelineStage.RIG, payload=payload)

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        self.availability_calls += 1
        if not context.has_output(PipelineStage.GEOMETRY):
            return ImplementationAvailability.unavailable('Geometry missing.')
        return ImplementationAvailability.ready_state()

class ExportImplementation(FakeImplementation):

    def __init__(self, *, payload: Any='export-data') -> None:
        super().__init__(identifier='glb', stage=PipelineStage.EXPORT, payload=payload)

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        self.availability_calls += 1
        if not context.has_output(PipelineStage.GEOMETRY):
            return ImplementationAvailability.unavailable('Geometry missing.')
        return ImplementationAvailability.ready_state()

class DirectContextOutputImplementation(FakeImplementation):
    """
    Implementation style where execute() stores its output
    directly instead of returning it through payload.
    """

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        self.execute_calls += 1
        context.set_output(self.descriptor.stage, 'direct-output')
        return StageExecutionResult.succeeded(stage=self.descriptor.stage, implementation_id=self.descriptor.identifier, payload=None)

def selection(stage: PipelineStage, implementation_id: str, *, enabled: bool=True) -> PipelineStageSelection:
    return PipelineStageSelection(stage=stage, implementation_id=implementation_id, enabled=enabled)

def full_plan(*, material: bool=True, rig: bool=True, export: bool=True) -> PipelinePlan:
    selections = [selection(PipelineStage.INPUT, 'projection-images'), selection(PipelineStage.GEOMETRY, 'native-hull')]
    if material:
        selections.append(selection(PipelineStage.MATERIAL, 'projected-color-v1.2'))
    if rig:
        selections.append(selection(PipelineStage.RIG, 'auto-rig'))
    if export:
        selections.append(selection(PipelineStage.EXPORT, 'glb'))
    return PipelinePlan(selections=tuple(selections))

def full_registry() -> tuple[PipelineRegistry, InputImplementation, GeometryImplementation, MaterialImplementation, RigImplementation, ExportImplementation]:
    registry = PipelineRegistry()
    input_implementation = InputImplementation()
    geometry = GeometryImplementation()
    material = MaterialImplementation()
    rig = RigImplementation()
    exporter = ExportImplementation()
    for implementation in (input_implementation, geometry, material, rig, exporter):
        registry.register(implementation)
    return (registry, input_implementation, geometry, material, rig, exporter)
