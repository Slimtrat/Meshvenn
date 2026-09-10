from __future__ import annotations

import sys
import unittest

from pathlib import Path
from typing import Any


# ---------------------------------------------------------
# Repository import
# ---------------------------------------------------------

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.pipeline_contracts import (
    AvailabilityState,
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelinePlan,
    PipelineStage,
    PipelineStageSelection,
    StageExecutionResult,
    StageResultState,
)
from core.pipeline_registry import (
    PipelineRegistry,
)
from core.pipeline_runner import (
    PipelineExecutionError,
    PipelineExecutionReport,
    PipelineRunIssue,
    PipelineRunOptions,
    PipelineRunner,
    StageRunRecord,
    run_pipeline,
)


# ---------------------------------------------------------
# Test implementation
# ---------------------------------------------------------

class FakeImplementation:
    def __init__(
        self,
        *,
        identifier: str,
        stage: PipelineStage,
        payload: Any = None,
        availability: (
            ImplementationAvailability
            | None
        ) = None,
        result_state: StageResultState = (
            StageResultState.SUCCESS
        ),
        message: str = "",
        metrics: dict[
            str,
            Any,
        ]
        | None = None,
        metadata: dict[
            str,
            Any,
        ]
        | None = None,
    ) -> None:
        self._descriptor = (
            ImplementationDescriptor(
                identifier=identifier,
                stage=stage,
                label=identifier,
                description=(
                    f"Fake {stage.value} implementation"
                ),
            )
        )

        self.payload = payload

        self._availability = (
            availability
            or (
                ImplementationAvailability
                .ready_state()
            )
        )

        self.result_state = (
            result_state
        )

        self.message = message

        self.metrics = (
            metrics
            or {}
        )

        self.metadata = (
            metadata
            or {}
        )

        self.availability_calls = 0

        self.execute_calls = 0

        self.received_contexts: list[
            PipelineContext
        ] = []

    @property
    def descriptor(
        self,
    ) -> ImplementationDescriptor:
        return (
            self._descriptor
        )

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        self.availability_calls += 1

        self.received_contexts.append(
            context
        )

        return (
            self._availability
        )

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        self.execute_calls += 1

        self.received_contexts.append(
            context
        )

        if (
            self.result_state
            == StageResultState.SUCCESS
        ):
            return (
                StageExecutionResult
                .succeeded(
                    stage=(
                        self.descriptor.stage
                    ),
                    implementation_id=(
                        self.descriptor.identifier
                    ),
                    payload=(
                        self.payload
                    ),
                    message=(
                        self.message
                    ),
                    metrics=(
                        self.metrics
                    ),
                    metadata=(
                        self.metadata
                    ),
                )
            )

        if (
            self.result_state
            == StageResultState.SKIPPED
        ):
            return (
                StageExecutionResult
                .skipped_result(
                    stage=(
                        self.descriptor.stage
                    ),
                    implementation_id=(
                        self.descriptor.identifier
                    ),
                    message=(
                        self.message
                    ),
                    metadata=(
                        self.metadata
                    ),
                )
            )

        return (
            StageExecutionResult
            .failed_result(
                stage=(
                    self.descriptor.stage
                ),
                implementation_id=(
                    self.descriptor.identifier
                ),
                message=(
                    self.message
                    or "Fake failure."
                ),
                metadata=(
                    self.metadata
                ),
            )
        )


class ExplodingImplementation(
    FakeImplementation
):
    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        self.execute_calls += 1

        raise RuntimeError(
            "execution exploded"
        )


class ExplodingAvailabilityImplementation(
    FakeImplementation
):
    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        self.availability_calls += 1

        raise RuntimeError(
            "availability exploded"
        )


class InvalidAvailabilityImplementation(
    FakeImplementation
):
    def availability(
        self,
        context: PipelineContext,
    ):
        self.availability_calls += 1

        return "ready"


class InvalidResultImplementation(
    FakeImplementation
):
    def execute(
        self,
        context: PipelineContext,
    ):
        self.execute_calls += 1

        return "success"


class WrongStageResultImplementation(
    FakeImplementation
):
    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        self.execute_calls += 1

        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    PipelineStage.RIG
                ),
                implementation_id=(
                    self.descriptor.identifier
                ),
            )
        )


class WrongIdResultImplementation(
    FakeImplementation
):
    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        self.execute_calls += 1

        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    self.descriptor.stage
                ),
                implementation_id=(
                    "another-implementation"
                ),
            )
        )


# ---------------------------------------------------------
# Context-aware implementations
# ---------------------------------------------------------

class InputImplementation(
    FakeImplementation
):
    def __init__(
        self,
        *,
        payload: Any = "input-data",
    ) -> None:
        super().__init__(
            identifier="projection-images",
            stage=(
                PipelineStage.INPUT
            ),
            payload=payload,
        )


class GeometryImplementation(
    FakeImplementation
):
    def __init__(
        self,
        *,
        payload: Any = "geometry-data",
    ) -> None:
        super().__init__(
            identifier="native-hull",
            stage=(
                PipelineStage.GEOMETRY
            ),
            payload=payload,
        )

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        self.availability_calls += 1

        if not context.has_output(
            PipelineStage.INPUT
        ):
            return (
                ImplementationAvailability
                .unavailable(
                    "Input missing."
                )
            )

        return (
            ImplementationAvailability
            .ready_state()
        )


class MaterialImplementation(
    FakeImplementation
):
    def __init__(
        self,
        *,
        payload: Any = "material-data",
    ) -> None:
        super().__init__(
            identifier="projected-color-v1.2",
            stage=(
                PipelineStage.MATERIAL
            ),
            payload=payload,
        )

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        self.availability_calls += 1

        if not context.has_output(
            PipelineStage.GEOMETRY
        ):
            return (
                ImplementationAvailability
                .unavailable(
                    "Geometry missing."
                )
            )

        return (
            ImplementationAvailability
            .ready_state()
        )


class RigImplementation(
    FakeImplementation
):
    def __init__(
        self,
        *,
        payload: Any = "rig-data",
    ) -> None:
        super().__init__(
            identifier="auto-rig",
            stage=(
                PipelineStage.RIG
            ),
            payload=payload,
        )

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        self.availability_calls += 1

        if not context.has_output(
            PipelineStage.GEOMETRY
        ):
            return (
                ImplementationAvailability
                .unavailable(
                    "Geometry missing."
                )
            )

        return (
            ImplementationAvailability
            .ready_state()
        )


class ExportImplementation(
    FakeImplementation
):
    def __init__(
        self,
        *,
        payload: Any = "export-data",
    ) -> None:
        super().__init__(
            identifier="glb",
            stage=(
                PipelineStage.EXPORT
            ),
            payload=payload,
        )

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        self.availability_calls += 1

        if not context.has_output(
            PipelineStage.GEOMETRY
        ):
            return (
                ImplementationAvailability
                .unavailable(
                    "Geometry missing."
                )
            )

        return (
            ImplementationAvailability
            .ready_state()
        )


class DirectContextOutputImplementation(
    FakeImplementation
):
    """
    Implementation style where execute() stores its output
    directly instead of returning it through payload.
    """

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        self.execute_calls += 1

        context.set_output(
            self.descriptor.stage,
            "direct-output",
        )

        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    self.descriptor.stage
                ),
                implementation_id=(
                    self.descriptor.identifier
                ),
                payload=None,
            )
        )


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def selection(
    stage: PipelineStage,
    implementation_id: str,
    *,
    enabled: bool = True,
) -> PipelineStageSelection:
    return PipelineStageSelection(
        stage=stage,
        implementation_id=(
            implementation_id
        ),
        enabled=enabled,
    )


def full_plan(
    *,
    material: bool = True,
    rig: bool = True,
    export: bool = True,
) -> PipelinePlan:
    selections = [
        selection(
            PipelineStage.INPUT,
            "projection-images",
        ),
        selection(
            PipelineStage.GEOMETRY,
            "native-hull",
        ),
    ]

    if material:
        selections.append(
            selection(
                PipelineStage.MATERIAL,
                "projected-color-v1.2",
            )
        )

    if rig:
        selections.append(
            selection(
                PipelineStage.RIG,
                "auto-rig",
            )
        )

    if export:
        selections.append(
            selection(
                PipelineStage.EXPORT,
                "glb",
            )
        )

    return PipelinePlan(
        selections=tuple(
            selections
        )
    )


def full_registry() -> tuple[
    PipelineRegistry,
    InputImplementation,
    GeometryImplementation,
    MaterialImplementation,
    RigImplementation,
    ExportImplementation,
]:
    registry = (
        PipelineRegistry()
    )

    input_implementation = (
        InputImplementation()
    )

    geometry = (
        GeometryImplementation()
    )

    material = (
        MaterialImplementation()
    )

    rig = (
        RigImplementation()
    )

    exporter = (
        ExportImplementation()
    )

    for implementation in (
        input_implementation,
        geometry,
        material,
        rig,
        exporter,
    ):
        registry.register(
            implementation
        )

    return (
        registry,
        input_implementation,
        geometry,
        material,
        rig,
        exporter,
    )


# ---------------------------------------------------------
# StageRunRecord
# ---------------------------------------------------------

class StageRunRecordTests(
    unittest.TestCase
):
    def test_properties_forward_result_state(
        self,
    ) -> None:
        selected = selection(
            PipelineStage.INPUT,
            "projection-images",
        )

        result = (
            StageExecutionResult
            .succeeded(
                stage=(
                    PipelineStage.INPUT
                ),
                implementation_id=(
                    "projection-images"
                ),
            )
        )

        record = StageRunRecord(
            selection=selected,
            result=result,
            duration_seconds=0.1,
        )

        self.assertEqual(
            record.stage,
            PipelineStage.INPUT,
        )

        self.assertEqual(
            record.implementation_id,
            "projection-images",
        )

        self.assertTrue(
            record.success
        )

        self.assertFalse(
            record.failed
        )

        self.assertFalse(
            record.skipped
        )


# ---------------------------------------------------------
# Preflight
# ---------------------------------------------------------

class PreflightTests(
    unittest.TestCase
):
    def test_complete_plan_passes_preflight(
        self,
    ) -> None:
        (
            registry,
            *_,
        ) = full_registry()

        runner = PipelineRunner(
            registry
        )

        issues = runner.preflight(
            full_plan(),
            PipelineContext(),
        )

        self.assertEqual(
            issues,
            (),
        )

    def test_missing_input_stage_is_reported(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            GeometryImplementation()
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
            )
        )

        issues = (
            PipelineRunner(
                registry
            )
            .preflight(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            any(
                issue.stage
                == PipelineStage.INPUT
                for issue
                in issues
            )
        )

    def test_missing_geometry_stage_is_reported(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                ),
            )
        )

        issues = (
            PipelineRunner(
                registry
            )
            .preflight(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            any(
                issue.stage
                == PipelineStage.GEOMETRY
                for issue
                in issues
            )
        )

    def test_existing_input_output_satisfies_required_stage(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            GeometryImplementation()
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
            )
        )

        context = (
            PipelineContext()
        )

        context.set_output(
            PipelineStage.INPUT,
            "existing-input",
        )

        issues = (
            PipelineRunner(
                registry
            )
            .preflight(
                plan,
                context,
            )
        )

        self.assertEqual(
            issues,
            (),
        )

    def test_existing_geometry_output_allows_material_only_plan(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            MaterialImplementation()
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
            )
        )

        context = (
            PipelineContext()
        )

        context.set_output(
            PipelineStage.INPUT,
            "input",
        )

        context.set_output(
            PipelineStage.GEOMETRY,
            "geometry",
        )

        issues = (
            PipelineRunner(
                registry
            )
            .preflight(
                plan,
                context,
            )
        )

        self.assertEqual(
            issues,
            (),
        )

    def test_disabled_required_stage_is_reported(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        registry.register(
            GeometryImplementation()
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                    enabled=False,
                ),
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
            )
        )

        issues = (
            PipelineRunner(
                registry
            )
            .preflight(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            any(
                issue.stage
                == PipelineStage.INPUT
                for issue
                in issues
            )
        )

    def test_unknown_implementation_is_reported(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                ),
                selection(
                    PipelineStage.GEOMETRY,
                    "missing-geometry",
                ),
            )
        )

        issues = (
            PipelineRunner(
                registry
            )
            .preflight(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            any(
                issue.implementation_id
                == "missing-geometry"
                for issue
                in issues
            )
        )


# ---------------------------------------------------------
# Full pipeline success
# ---------------------------------------------------------

class SuccessfulPipelineTests(
    unittest.TestCase
):
    def test_full_pipeline_runs_in_stage_order(
        self,
    ) -> None:
        (
            registry,
            input_implementation,
            geometry,
            material,
            rig,
            exporter,
        ) = full_registry()

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(),
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertFalse(
            report.failed
        )

        self.assertFalse(
            report.aborted
        )

        self.assertEqual(
            [
                record.stage
                for record
                in report.records
            ],
            [
                PipelineStage.INPUT,
                PipelineStage.GEOMETRY,
                PipelineStage.MATERIAL,
                PipelineStage.RIG,
                PipelineStage.EXPORT,
            ],
        )

        self.assertEqual(
            input_implementation.execute_calls,
            1,
        )

        self.assertEqual(
            geometry.execute_calls,
            1,
        )

        self.assertEqual(
            material.execute_calls,
            1,
        )

        self.assertEqual(
            rig.execute_calls,
            1,
        )

        self.assertEqual(
            exporter.execute_calls,
            1,
        )

    def test_outputs_propagate_between_stages(
        self,
    ) -> None:
        (
            registry,
            *_,
        ) = full_registry()

        context = (
            PipelineContext()
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(),
                context,
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            context.get_output(
                PipelineStage.INPUT
            ),
            "input-data",
        )

        self.assertEqual(
            context.get_output(
                PipelineStage.GEOMETRY
            ),
            "geometry-data",
        )

        self.assertEqual(
            context.get_output(
                PipelineStage.MATERIAL
            ),
            "material-data",
        )

        self.assertEqual(
            context.get_output(
                PipelineStage.RIG
            ),
            "rig-data",
        )

        self.assertEqual(
            context.get_output(
                PipelineStage.EXPORT
            ),
            "export-data",
        )

    def test_same_context_is_used_by_all_stages(
        self,
    ) -> None:
        (
            registry,
            input_implementation,
            geometry,
            material,
            rig,
            exporter,
        ) = full_registry()

        context = (
            PipelineContext()
        )

        PipelineRunner(
            registry
        ).run(
            full_plan(),
            context,
        )

        for implementation in (
            input_implementation,
            geometry,
            material,
            rig,
            exporter,
        ):
            self.assertTrue(
                all(
                    received is context
                    for received
                    in implementation
                    .received_contexts
                )
            )

    def test_optional_stages_can_be_omitted(
        self,
    ) -> None:
        (
            registry,
            *_,
        ) = full_registry()

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            [
                record.stage
                for record
                in report.records
            ],
            [
                PipelineStage.INPUT,
                PipelineStage.GEOMETRY,
            ],
        )


# ---------------------------------------------------------
# Dynamic availability
# ---------------------------------------------------------

class AvailabilityTests(
    unittest.TestCase
):
    def test_geometry_availability_is_checked_after_input(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        input_implementation = (
            InputImplementation()
        )

        geometry = (
            GeometryImplementation()
        )

        registry.register(
            input_implementation
        )

        registry.register(
            geometry
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            geometry.availability_calls,
            1,
        )

        self.assertEqual(
            geometry.execute_calls,
            1,
        )

    def test_material_availability_can_depend_on_geometry_output(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        registry.register(
            GeometryImplementation()
        )

        material = (
            MaterialImplementation()
        )

        registry.register(
            material
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                ),
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            material.execute_calls,
            1,
        )

    def test_unavailable_stage_fails_without_execution(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        unavailable_geometry = (
            FakeImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
                availability=(
                    ImplementationAvailability
                    .unavailable(
                        "Native library missing."
                    )
                ),
            )
        )

        registry.register(
            unavailable_geometry
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.failed
        )

        self.assertTrue(
            report.aborted
        )

        self.assertEqual(
            unavailable_geometry.execute_calls,
            0,
        )

        geometry_record = (
            report.record_for(
                PipelineStage.GEOMETRY
            )
        )

        self.assertIsNotNone(
            geometry_record
        )

        self.assertTrue(
            geometry_record.failed
        )

        self.assertEqual(
            geometry_record
            .availability
            .state,
            AvailabilityState.UNAVAILABLE,
        )

    def test_availability_check_can_be_disabled(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        implementation = (
            FakeImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
                payload="geometry",
                availability=(
                    ImplementationAvailability
                    .unavailable(
                        "Disabled backend."
                    )
                ),
            )
        )

        registry.register(
            implementation
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
                options=(
                    PipelineRunOptions(
                        check_availability=False
                    )
                ),
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            implementation.availability_calls,
            0,
        )

        self.assertEqual(
            implementation.execute_calls,
            1,
        )


# ---------------------------------------------------------
# Dependency handling
# ---------------------------------------------------------

class DependencyTests(
    unittest.TestCase
):
    def test_material_only_can_use_existing_geometry(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        material = (
            MaterialImplementation()
        )

        registry.register(
            material
        )

        context = (
            PipelineContext()
        )

        context.set_output(
            PipelineStage.INPUT,
            "existing-input",
        )

        context.set_output(
            PipelineStage.GEOMETRY,
            "existing-mesh",
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                plan,
                context,
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            material.execute_calls,
            1,
        )

        self.assertEqual(
            context.get_output(
                PipelineStage.GEOMETRY
            ),
            "existing-mesh",
        )

    def test_missing_runtime_dependency_fails_stage(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        material = (
            MaterialImplementation()
        )

        registry.register(
            material
        )

        # INPUT and GEOMETRY satisfy preflight by being in
        # context initially, but geometry is deliberately
        # removed before _run_selection() through a small
        # custom runner hook.

        context = (
            PipelineContext()
        )

        context.set_output(
            PipelineStage.INPUT,
            "input",
        )

        context.set_output(
            PipelineStage.GEOMETRY,
            "mesh",
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
            )
        )

        runner = (
            PipelineRunner(
                registry
            )
        )

        self.assertEqual(
            runner.preflight(
                plan,
                context,
            ),
            (),
        )

        context.outputs.pop(
            PipelineStage.GEOMETRY
        )

        record = (
            runner._run_selection(
                plan.selections[0],
                context,
                PipelineRunOptions(),
            )
        )

        self.assertTrue(
            record.failed
        )

        self.assertIn(
            "geometry",
            record
            .result
            .message,
        )

        self.assertEqual(
            material.execute_calls,
            0,
        )


# ---------------------------------------------------------
# Disabled stages
# ---------------------------------------------------------

class DisabledStageTests(
    unittest.TestCase
):
    def test_disabled_optional_stage_is_skipped(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        registry.register(
            GeometryImplementation()
        )

        material = (
            MaterialImplementation()
        )

        registry.register(
            material
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                ),
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                    enabled=False,
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.success
        )

        material_record = (
            report.record_for(
                PipelineStage.MATERIAL
            )
        )

        self.assertIsNotNone(
            material_record
        )

        self.assertTrue(
            material_record.skipped
        )

        self.assertEqual(
            material.execute_calls,
            0,
        )


# ---------------------------------------------------------
# Stage failures
# ---------------------------------------------------------

class StageFailureTests(
    unittest.TestCase
):
    def test_failed_result_stops_pipeline_by_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        geometry = (
            FakeImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
                result_state=(
                    StageResultState.FAILED
                ),
                message="Geometry failed.",
            )
        )

        material = (
            MaterialImplementation()
        )

        registry.register(
            geometry
        )

        registry.register(
            material
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                ),
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.failed
        )

        self.assertTrue(
            report.aborted
        )

        self.assertEqual(
            geometry.execute_calls,
            1,
        )

        self.assertEqual(
            material.execute_calls,
            0,
        )

    def test_stop_on_failure_false_attempts_later_stages(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        geometry = (
            FakeImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
                result_state=(
                    StageResultState.FAILED
                ),
                message="Geometry failed.",
            )
        )

        material = (
            MaterialImplementation()
        )

        registry.register(
            geometry
        )

        registry.register(
            material
        )

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                ),
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                plan,
                PipelineContext(),
                options=(
                    PipelineRunOptions(
                        stop_on_failure=False
                    )
                ),
            )
        )

        self.assertTrue(
            report.failed
        )

        self.assertFalse(
            report.aborted
        )

        # Geometry never produced output, so Material is
        # reached but fails dependency validation before
        # execute().
        material_record = (
            report.record_for(
                PipelineStage.MATERIAL
            )
        )

        self.assertIsNotNone(
            material_record
        )

        self.assertTrue(
            material_record.failed
        )

        self.assertEqual(
            material.execute_calls,
            0,
        )


# ---------------------------------------------------------
# Exceptions
# ---------------------------------------------------------

class ExceptionTests(
    unittest.TestCase
):
    def test_execution_exception_becomes_failed_result(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        implementation = (
            ExplodingImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.failed
        )

        record = (
            report.record_for(
                PipelineStage.GEOMETRY
            )
        )

        self.assertIn(
            "execution exploded",
            record
            .result
            .message,
        )

        self.assertEqual(
            record
            .result
            .metadata[
                "exception_type"
            ],
            "RuntimeError",
        )

    def test_execution_exception_can_escape(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        registry.register(
            ExplodingImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            PipelineRunner(
                registry
            ).run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
                options=(
                    PipelineRunOptions(
                        catch_exceptions=False
                    )
                ),
            )

    def test_availability_exception_becomes_failure(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        implementation = (
            ExplodingAvailabilityImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.failed
        )

        self.assertIn(
            "availability exploded",
            report
            .record_for(
                PipelineStage.GEOMETRY
            )
            .result
            .message,
        )


# ---------------------------------------------------------
# Contract validation
# ---------------------------------------------------------

class ResultContractTests(
    unittest.TestCase
):
    def test_invalid_result_type_becomes_failure(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        implementation = (
            InvalidResultImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        record = (
            report.record_for(
                PipelineStage.GEOMETRY
            )
        )

        self.assertTrue(
            record.failed
        )

        self.assertIn(
            "StageExecutionResult",
            record
            .result
            .message,
        )

    def test_wrong_stage_result_becomes_failure(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        registry.register(
            WrongStageResultImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        record = (
            report.record_for(
                PipelineStage.GEOMETRY
            )
        )

        self.assertTrue(
            record.failed
        )

        self.assertIn(
            "instead of",
            record
            .result
            .message,
        )

    def test_wrong_implementation_id_becomes_failure(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        registry.register(
            WrongIdResultImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        record = (
            report.record_for(
                PipelineStage.GEOMETRY
            )
        )

        self.assertTrue(
            record.failed
        )

        self.assertIn(
            "another-implementation",
            record
            .result
            .message,
        )

    def test_invalid_availability_type_becomes_failure(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        implementation = (
            InvalidAvailabilityImplementation(
                identifier="native-hull",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        record = (
            report.record_for(
                PipelineStage.GEOMETRY
            )
        )

        self.assertTrue(
            record.failed
        )

        self.assertIn(
            "availability",
            record
            .result
            .message,
        )


# ---------------------------------------------------------
# Direct context output
# ---------------------------------------------------------

class DirectContextOutputTests(
    unittest.TestCase
):
    def test_implementation_can_store_output_directly(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        input_impl = (
            DirectContextOutputImplementation(
                identifier="projection-images",
                stage=(
                    PipelineStage.INPUT
                ),
            )
        )

        geometry = (
            GeometryImplementation()
        )

        registry.register(
            input_impl
        )

        registry.register(
            geometry
        )

        context = (
            PipelineContext()
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                context,
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            context.get_output(
                PipelineStage.INPUT
            ),
            "direct-output",
        )


# ---------------------------------------------------------
# Reports
# ---------------------------------------------------------

class ReportTests(
    unittest.TestCase
):
    def test_record_for_unknown_stage_returns_none(
        self,
    ) -> None:
        report = (
            PipelineExecutionReport(
                plan=PipelinePlan(
                    selections=()
                ),
                context=(
                    PipelineContext()
                ),
                records=(),
                issues=(),
                duration_seconds=0.0,
                aborted=False,
            )
        )

        self.assertIsNone(
            report.record_for(
                PipelineStage.RIG
            )
        )

        self.assertIsNone(
            report.result_for(
                PipelineStage.RIG
            )
        )

    def test_failure_message_contains_stage_and_implementation(
        self,
    ) -> None:
        selected = selection(
            PipelineStage.GEOMETRY,
            "native-hull",
        )

        record = StageRunRecord(
            selection=selected,
            result=(
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        "native-hull"
                    ),
                    message="No mesh.",
                )
            ),
            duration_seconds=0.0,
        )

        report = (
            PipelineExecutionReport(
                plan=PipelinePlan(
                    selections=(
                        selected,
                    )
                ),
                context=(
                    PipelineContext()
                ),
                records=(
                    record,
                ),
                issues=(),
                duration_seconds=0.0,
                aborted=True,
            )
        )

        self.assertIn(
            "geometry",
            report.failure_message,
        )

        self.assertIn(
            "native-hull",
            report.failure_message,
        )

        self.assertIn(
            "No mesh.",
            report.failure_message,
        )

    def test_failure_message_contains_preflight_issue(
        self,
    ) -> None:
        report = (
            PipelineExecutionReport(
                plan=PipelinePlan(
                    selections=()
                ),
                context=(
                    PipelineContext()
                ),
                records=(),
                issues=(
                    PipelineRunIssue(
                        stage=(
                            PipelineStage.INPUT
                        ),
                        implementation_id=None,
                        message="Missing input.",
                    ),
                ),
                duration_seconds=0.0,
                aborted=True,
            )
        )

        self.assertIn(
            "Missing input.",
            report.failure_message,
        )

    def test_raise_for_failure_does_nothing_for_success(
        self,
    ) -> None:
        report = (
            PipelineExecutionReport(
                plan=PipelinePlan(
                    selections=()
                ),
                context=(
                    PipelineContext()
                ),
                records=(),
                issues=(),
                duration_seconds=0.0,
                aborted=False,
            )
        )

        report.raise_for_failure()

    def test_raise_for_failure_raises_report_error(
        self,
    ) -> None:
        report = (
            PipelineExecutionReport(
                plan=PipelinePlan(
                    selections=()
                ),
                context=(
                    PipelineContext()
                ),
                records=(),
                issues=(
                    PipelineRunIssue(
                        stage=None,
                        implementation_id=None,
                        message="Broken pipeline.",
                    ),
                ),
                duration_seconds=0.0,
                aborted=True,
            )
        )

        with self.assertRaises(
            PipelineExecutionError
        ) as error:
            report.raise_for_failure()

        self.assertIs(
            error.exception.report,
            report,
        )


# ---------------------------------------------------------
# Metrics and metadata
# ---------------------------------------------------------

class MetricsTests(
    unittest.TestCase
):
    def test_metrics_are_preserved(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            FakeImplementation(
                identifier="projection-images",
                stage=(
                    PipelineStage.INPUT
                ),
                payload="input",
                metrics={
                    "views": 10
                },
                metadata={
                    "source": "sheet"
                },
            )
        )

        registry.register(
            GeometryImplementation()
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(
                    material=False,
                    rig=False,
                    export=False,
                ),
                PipelineContext(),
            )
        )

        record = (
            report.record_for(
                PipelineStage.INPUT
            )
        )

        self.assertEqual(
            record
            .result
            .metrics[
                "views"
            ],
            10,
        )

        self.assertEqual(
            record
            .result
            .metadata[
                "source"
            ],
            "sheet",
        )


# ---------------------------------------------------------
# Convenience facade
# ---------------------------------------------------------

class ConvenienceFacadeTests(
    unittest.TestCase
):
    def test_run_pipeline_wrapper_uses_registry(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            InputImplementation()
        )

        registry.register(
            GeometryImplementation()
        )

        report = run_pipeline(
            registry,
            full_plan(
                material=False,
                rig=False,
                export=False,
            ),
            PipelineContext(),
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            len(
                report.records
            ),
            2,
        )


# ---------------------------------------------------------
# Stage ordering
# ---------------------------------------------------------

class StageOrderingTests(
    unittest.TestCase
):
    def test_plan_input_order_does_not_change_execution_order(
        self,
    ) -> None:
        (
            registry,
            *_,
        ) = full_registry()

        plan = PipelinePlan(
            selections=(
                selection(
                    PipelineStage.EXPORT,
                    "glb",
                ),
                selection(
                    PipelineStage.RIG,
                    "auto-rig",
                ),
                selection(
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
                selection(
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
                selection(
                    PipelineStage.INPUT,
                    "projection-images",
                ),
            )
        )

        report = (
            PipelineRunner(
                registry
            )
            .run(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            report.success
        )

        self.assertEqual(
            [
                record.stage
                for record
                in report.records
            ],
            [
                PipelineStage.INPUT,
                PipelineStage.GEOMETRY,
                PipelineStage.MATERIAL,
                PipelineStage.RIG,
                PipelineStage.EXPORT,
            ],
        )


# ---------------------------------------------------------
# Timing
# ---------------------------------------------------------

class TimingTests(
    unittest.TestCase
):
    def test_stage_duration_is_non_negative(
        self,
    ) -> None:
        (
            registry,
            *_,
        ) = full_registry()

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(),
                PipelineContext(),
            )
        )

        for record in (
            report.records
        ):
            self.assertGreaterEqual(
                record.duration_seconds,
                0.0,
            )

    def test_total_duration_is_non_negative(
        self,
    ) -> None:
        (
            registry,
            *_,
        ) = full_registry()

        report = (
            PipelineRunner(
                registry
            )
            .run(
                full_plan(),
                PipelineContext(),
            )
        )

        self.assertGreaterEqual(
            report.duration_seconds,
            0.0,
        )


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------

if __name__ == "__main__":
    unittest.main()