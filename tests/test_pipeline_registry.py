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
)
from core.pipeline_registry import (
    DuplicateImplementationError,
    InvalidImplementationError,
    PipelineRegistry,
    PipelineRegistryError,
    StageMismatchError,
    UnknownImplementationError,
    build_default_plan,
    register_many,
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
        label: str | None = None,
        availability: (
            ImplementationAvailability
            | None
        ) = None,
        payload: Any = None,
    ) -> None:
        self._descriptor = (
            ImplementationDescriptor(
                identifier=identifier,
                stage=stage,
                label=(
                    label
                    or identifier
                ),
                description=(
                    f"Fake implementation "
                    f"for {stage.value}"
                ),
            )
        )

        self._availability = (
            availability
            or ImplementationAvailability
            .ready_state()
        )

        self.payload = payload

        self.availability_calls = 0
        self.execute_calls = 0

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

        return (
            self._availability
        )

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        self.execute_calls += 1

        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    self
                    .descriptor
                    .stage
                ),
                implementation_id=(
                    self
                    .descriptor
                    .identifier
                ),
                payload=(
                    self.payload
                ),
            )
        )


class InvalidAvailabilityImplementation(
    FakeImplementation
):
    def availability(
        self,
        context: PipelineContext,
    ):
        return "ready"


class ExplodingAvailabilityImplementation(
    FakeImplementation
):
    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        raise RuntimeError(
            "boom"
        )


class MissingAvailabilityImplementation:
    def __init__(
        self,
    ) -> None:
        self.descriptor = (
            ImplementationDescriptor(
                identifier="missing-availability",
                stage=(
                    PipelineStage.GEOMETRY
                ),
                label="Missing Availability",
                description="Invalid test implementation.",
            )
        )

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    PipelineStage.GEOMETRY
                ),
                implementation_id=(
                    "missing-availability"
                ),
            )
        )


class MissingExecuteImplementation:
    def __init__(
        self,
    ) -> None:
        self.descriptor = (
            ImplementationDescriptor(
                identifier="missing-execute",
                stage=(
                    PipelineStage.GEOMETRY
                ),
                label="Missing Execute",
                description="Invalid test implementation.",
            )
        )

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        return (
            ImplementationAvailability
            .ready_state()
        )


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def geometry_impl(
    identifier: str = "geometry-a",
    **kwargs,
) -> FakeImplementation:
    return FakeImplementation(
        identifier=identifier,
        stage=(
            PipelineStage.GEOMETRY
        ),
        **kwargs,
    )


def material_impl(
    identifier: str = "material-a",
    **kwargs,
) -> FakeImplementation:
    return FakeImplementation(
        identifier=identifier,
        stage=(
            PipelineStage.MATERIAL
        ),
        **kwargs,
    )


def rig_impl(
    identifier: str = "rig-a",
    **kwargs,
) -> FakeImplementation:
    return FakeImplementation(
        identifier=identifier,
        stage=(
            PipelineStage.RIG
        ),
        **kwargs,
    )


# ---------------------------------------------------------
# Empty registry
# ---------------------------------------------------------

class EmptyRegistryTests(
    unittest.TestCase
):
    def test_new_registry_is_empty(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        self.assertEqual(
            len(registry),
            0,
        )

        self.assertFalse(
            registry
        )

        self.assertEqual(
            registry.entries(),
            (),
        )

    def test_stage_has_no_implementations(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        self.assertFalse(
            registry.has_stage(
                PipelineStage.GEOMETRY
            )
        )

        self.assertIsNone(
            registry.default_id(
                PipelineStage.GEOMETRY
            )
        )

        self.assertIsNone(
            registry.default(
                PipelineStage.GEOMETRY
            )
        )


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------

class RegistrationTests(
    unittest.TestCase
):
    def test_register_adds_implementation(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            geometry_impl()
        )

        returned = registry.register(
            implementation
        )

        self.assertIs(
            returned,
            implementation,
        )

        self.assertEqual(
            len(registry),
            1,
        )

        self.assertIn(
            "geometry-a",
            registry,
        )

        self.assertIs(
            registry.get(
                "geometry-a"
            ),
            implementation,
        )

    def test_first_implementation_becomes_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            geometry_impl(
                "native-hull"
            )
        )

        registry.register(
            implementation,
            default=False,
        )

        self.assertEqual(
            registry.default_id(
                PipelineStage.GEOMETRY
            ),
            "native-hull",
        )

        self.assertIs(
            registry.default(
                PipelineStage.GEOMETRY
            ),
            implementation,
        )

    def test_second_implementation_does_not_replace_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        first = geometry_impl(
            "geometry-a"
        )

        second = geometry_impl(
            "geometry-b"
        )

        registry.register(
            first
        )

        registry.register(
            second
        )

        self.assertEqual(
            registry.default_id(
                PipelineStage.GEOMETRY
            ),
            "geometry-a",
        )

    def test_explicit_default_replaces_previous_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            ),
            default=True,
        )

        self.assertEqual(
            registry.default_id(
                PipelineStage.GEOMETRY
            ),
            "geometry-b",
        )

        entries = registry.entries(
            PipelineStage.GEOMETRY
        )

        defaults = [
            entry.descriptor.identifier
            for entry in entries
            if entry.is_default
        ]

        self.assertEqual(
            defaults,
            [
                "geometry-b"
            ],
        )

    def test_duplicate_registration_is_rejected(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "same"
            )
        )

        with self.assertRaises(
            DuplicateImplementationError
        ):
            registry.register(
                geometry_impl(
                    "same"
                )
            )

    def test_none_implementation_is_rejected(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        with self.assertRaises(
            InvalidImplementationError
        ):
            registry.register(
                None
            )

    def test_missing_availability_is_rejected(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        with self.assertRaises(
            InvalidImplementationError
        ):
            registry.register(
                MissingAvailabilityImplementation()
            )

    def test_missing_execute_is_rejected(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        with self.assertRaises(
            InvalidImplementationError
        ):
            registry.register(
                MissingExecuteImplementation()
            )


# ---------------------------------------------------------
# Replacement
# ---------------------------------------------------------

class ReplacementTests(
    unittest.TestCase
):
    def test_replace_updates_instance(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        original = geometry_impl(
            "native-hull",
            label="Original",
        )

        replacement = geometry_impl(
            "native-hull",
            label="Reloaded",
        )

        registry.register(
            original
        )

        registry.register(
            replacement,
            replace=True,
        )

        self.assertIs(
            registry.get(
                "native-hull"
            ),
            replacement,
        )

        self.assertEqual(
            registry
            .require_entry(
                "native-hull"
            )
            .descriptor
            .label,
            "Reloaded",
        )

    def test_replace_preserves_registration_position(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            )
        )

        replacement = geometry_impl(
            "geometry-a",
            label="Reloaded A",
        )

        registry.register(
            replacement,
            replace=True,
        )

        self.assertEqual(
            registry.implementation_ids(
                PipelineStage.GEOMETRY
            ),
            (
                "geometry-a",
                "geometry-b",
            ),
        )

    def test_replace_preserves_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            ),
            replace=True,
        )

        self.assertEqual(
            registry.default_id(
                PipelineStage.GEOMETRY
            ),
            "geometry-a",
        )

    def test_replace_can_make_existing_implementation_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            ),
            replace=True,
            default=True,
        )

        self.assertEqual(
            registry.default_id(
                PipelineStage.GEOMETRY
            ),
            "geometry-b",
        )

    def test_replace_cannot_change_stage(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "shared-id"
            )
        )

        incompatible = (
            material_impl(
                "shared-id"
            )
        )

        with self.assertRaises(
            StageMismatchError
        ):
            registry.register(
                incompatible,
                replace=True,
            )


# ---------------------------------------------------------
# Unregister
# ---------------------------------------------------------

class UnregisterTests(
    unittest.TestCase
):
    def test_unregister_removes_implementation(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            geometry_impl()
        )

        registry.register(
            implementation
        )

        removed = registry.unregister(
            "geometry-a"
        )

        self.assertIs(
            removed,
            implementation,
        )

        self.assertNotIn(
            "geometry-a",
            registry,
        )

    def test_unregister_unknown_returns_none(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        self.assertIsNone(
            registry.unregister(
                "unknown"
            )
        )

    def test_removing_default_promotes_first_remaining(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-c"
            )
        )

        registry.unregister(
            "geometry-a"
        )

        self.assertEqual(
            registry.default_id(
                PipelineStage.GEOMETRY
            ),
            "geometry-b",
        )

    def test_removing_last_default_leaves_stage_without_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.unregister(
            "geometry-a"
        )

        self.assertIsNone(
            registry.default_id(
                PipelineStage.GEOMETRY
            )
        )

        self.assertFalse(
            registry.has_stage(
                PipelineStage.GEOMETRY
            )
        )


# ---------------------------------------------------------
# Lookup
# ---------------------------------------------------------

class LookupTests(
    unittest.TestCase
):
    def test_require_returns_registered_implementation(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            material_impl(
                "projected-color-v1.2"
            )
        )

        registry.register(
            implementation
        )

        self.assertIs(
            registry.require(
                "projected-color-v1.2"
            ),
            implementation,
        )

    def test_require_unknown_raises(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        with self.assertRaises(
            UnknownImplementationError
        ):
            registry.require(
                "unknown"
            )

    def test_require_can_validate_stage(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            material_impl(
                "projected-color-v1.2"
            )
        )

        registry.register(
            implementation
        )

        self.assertIs(
            registry.require(
                "projected-color-v1.2",
                stage=(
                    PipelineStage.MATERIAL
                ),
            ),
            implementation,
        )

    def test_require_wrong_stage_raises(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            material_impl(
                "projected-color-v1.2"
            )
        )

        with self.assertRaises(
            StageMismatchError
        ):
            registry.require(
                "projected-color-v1.2",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )


# ---------------------------------------------------------
# Defaults
# ---------------------------------------------------------

class DefaultTests(
    unittest.TestCase
):
    def test_set_default_switches_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            )
        )

        registry.set_default(
            PipelineStage.GEOMETRY,
            "geometry-b",
        )

        self.assertEqual(
            registry.default_id(
                PipelineStage.GEOMETRY
            ),
            "geometry-b",
        )

    def test_set_default_rejects_wrong_stage(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            material_impl(
                "material-a"
            )
        )

        with self.assertRaises(
            StageMismatchError
        ):
            registry.set_default(
                PipelineStage.GEOMETRY,
                "material-a",
            )

    def test_resolve_stage_uses_default(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            geometry_impl(
                "native-hull"
            )
        )

        registry.register(
            implementation
        )

        self.assertIs(
            registry.resolve_stage(
                PipelineStage.GEOMETRY
            ),
            implementation,
        )

    def test_resolve_stage_can_use_explicit_id(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        first = geometry_impl(
            "geometry-a"
        )

        second = geometry_impl(
            "geometry-b"
        )

        registry.register(
            first
        )

        registry.register(
            second
        )

        self.assertIs(
            registry.resolve_stage(
                PipelineStage.GEOMETRY,
                "geometry-b",
            ),
            second,
        )

    def test_resolve_stage_without_implementation_raises(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        with self.assertRaises(
            UnknownImplementationError
        ):
            registry.resolve_stage(
                PipelineStage.RIG
            )


# ---------------------------------------------------------
# Ordering
# ---------------------------------------------------------

class OrderingTests(
    unittest.TestCase
):
    def test_entries_are_grouped_in_pipeline_order(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            rig_impl(
                "rig-a"
            )
        )

        registry.register(
            material_impl(
                "material-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        stages = [
            entry.descriptor.stage
            for entry
            in registry.entries()
        ]

        self.assertEqual(
            stages,
            [
                PipelineStage.GEOMETRY,
                PipelineStage.MATERIAL,
                PipelineStage.RIG,
            ],
        )

    def test_registration_order_is_preserved_inside_stage(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-c"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            )
        )

        self.assertEqual(
            registry.implementation_ids(
                PipelineStage.GEOMETRY
            ),
            (
                "geometry-c",
                "geometry-a",
                "geometry-b",
            ),
        )

    def test_iteration_yields_implementations(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        geometry = geometry_impl(
            "geometry-a"
        )

        material = material_impl(
            "material-a"
        )

        registry.register(
            material
        )

        registry.register(
            geometry
        )

        self.assertEqual(
            list(
                registry
            ),
            [
                geometry,
                material,
            ],
        )


# ---------------------------------------------------------
# Clear
# ---------------------------------------------------------

class ClearTests(
    unittest.TestCase
):
    def test_clear_resets_registry(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            material_impl(
                "material-a"
            )
        )

        registry.clear()

        self.assertEqual(
            len(registry),
            0,
        )

        self.assertEqual(
            registry.entries(),
            (),
        )

        self.assertIsNone(
            registry.default_id(
                PipelineStage.GEOMETRY
            )
        )

        self.assertIsNone(
            registry.default_id(
                PipelineStage.MATERIAL
            )
        )


# ---------------------------------------------------------
# Availability
# ---------------------------------------------------------

class AvailabilityTests(
    unittest.TestCase
):
    def test_ready_implementation_is_available(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            geometry_impl(
                "native-hull"
            )
        )

        registry.register(
            implementation
        )

        availability = (
            registry.availability(
                "native-hull",
                PipelineContext(),
            )
        )

        self.assertTrue(
            availability.available
        )

        self.assertTrue(
            availability.ready
        )

        self.assertEqual(
            availability.state,
            AvailabilityState.READY,
        )

    def test_degraded_implementation_is_still_available(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            geometry_impl(
                "degraded",
                availability=(
                    ImplementationAvailability
                    .degraded(
                        "Fallback backend active."
                    )
                ),
            )
        )

        registry.register(
            implementation
        )

        availability = (
            registry.availability(
                "degraded",
                PipelineContext(),
            )
        )

        self.assertTrue(
            availability.available
        )

        self.assertFalse(
            availability.ready
        )

    def test_unavailable_implementation_is_not_available(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            rig_impl(
                "auto-rig",
                availability=(
                    ImplementationAvailability
                    .unavailable(
                        "Not implemented yet."
                    )
                ),
            )
        )

        registry.register(
            implementation
        )

        availability = (
            registry.availability(
                "auto-rig",
                PipelineContext(),
            )
        )

        self.assertFalse(
            availability.available
        )

        self.assertEqual(
            availability.reason,
            "Not implemented yet.",
        )

    def test_availability_entries_include_default_flag(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "geometry-a"
            )
        )

        registry.register(
            geometry_impl(
                "geometry-b"
            )
        )

        entries = (
            registry
            .availability_entries(
                PipelineStage.GEOMETRY,
                PipelineContext(),
            )
        )

        self.assertEqual(
            len(entries),
            2,
        )

        self.assertTrue(
            entries[0].is_default
        )

        self.assertFalse(
            entries[1].is_default
        )

    def test_available_entries_filter_unavailable(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "ready"
            )
        )

        registry.register(
            geometry_impl(
                "offline",
                availability=(
                    ImplementationAvailability
                    .unavailable(
                        "Offline."
                    )
                ),
            )
        )

        entries = (
            registry
            .available_entries(
                PipelineStage.GEOMETRY,
                PipelineContext(),
            )
        )

        self.assertEqual(
            [
                entry.identifier
                for entry in entries
            ],
            [
                "ready"
            ],
        )

    def test_invalid_availability_result_is_rejected(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            InvalidAvailabilityImplementation(
                identifier="invalid",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        with self.assertRaises(
            InvalidImplementationError
        ):
            registry.availability(
                "invalid",
                PipelineContext(),
            )


# ---------------------------------------------------------
# Selection
# ---------------------------------------------------------

class SelectionTests(
    unittest.TestCase
):
    def test_resolve_selection_returns_implementation(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            material_impl(
                "projected-color-v1.2"
            )
        )

        registry.register(
            implementation
        )

        selection = (
            PipelineStageSelection(
                stage=(
                    PipelineStage.MATERIAL
                ),
                implementation_id=(
                    "projected-color-v1.2"
                ),
            )
        )

        self.assertIs(
            registry.resolve_selection(
                selection
            ),
            implementation,
        )

    def test_resolve_selection_rejects_stage_mismatch(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            material_impl(
                "projected-color-v1.2"
            )
        )

        selection = (
            PipelineStageSelection(
                stage=(
                    PipelineStage.GEOMETRY
                ),
                implementation_id=(
                    "projected-color-v1.2"
                ),
            )
        )

        with self.assertRaises(
            StageMismatchError
        ):
            registry.resolve_selection(
                selection
            )


# ---------------------------------------------------------
# Plan validation
# ---------------------------------------------------------

class PlanValidationTests(
    unittest.TestCase
):
    def test_valid_plan_passes(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "native-hull"
            )
        )

        registry.register(
            material_impl(
                "projected-color-v1.2"
            )
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        "native-hull"
                    ),
                ),
                PipelineStageSelection(
                    stage=(
                        PipelineStage.MATERIAL
                    ),
                    implementation_id=(
                        "projected-color-v1.2"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            result.valid
        )

        self.assertEqual(
            result.issues,
            (),
        )

    def test_unknown_implementation_is_reported(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        "missing-engine"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
            )
        )

        self.assertFalse(
            result.valid
        )

        self.assertEqual(
            len(
                result.issues
            ),
            1,
        )

        self.assertEqual(
            result
            .issues[0]
            .implementation_id,
            "missing-engine",
        )

    def test_stage_mismatch_is_reported(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            material_impl(
                "projected-color-v1.2"
            )
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        "projected-color-v1.2"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
            )
        )

        self.assertFalse(
            result.valid
        )

        self.assertIn(
            "material",
            result
            .issues[0]
            .message,
        )

    def test_unavailable_implementation_is_reported(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            rig_impl(
                "auto-rig",
                availability=(
                    ImplementationAvailability
                    .unavailable(
                        "Rig backend unavailable."
                    )
                ),
            )
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.RIG
                    ),
                    implementation_id=(
                        "auto-rig"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
            )
        )

        self.assertFalse(
            result.valid
        )

        self.assertEqual(
            result
            .issues[0]
            .message,
            "Rig backend unavailable.",
        )

    def test_disabled_selection_is_not_validated(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.RIG
                    ),
                    implementation_id=(
                        "missing-rig"
                    ),
                    enabled=False,
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
            )
        )

        self.assertTrue(
            result.valid
        )

    def test_availability_can_be_skipped(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            rig_impl(
                "auto-rig",
                availability=(
                    ImplementationAvailability
                    .unavailable(
                        "Not ready."
                    )
                ),
            )
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.RIG
                    ),
                    implementation_id=(
                        "auto-rig"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
                check_availability=False,
            )
        )

        self.assertTrue(
            result.valid
        )

    def test_availability_exception_becomes_validation_issue(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            ExplodingAvailabilityImplementation(
                identifier="exploding",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        "exploding"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
            )
        )

        self.assertFalse(
            result.valid
        )

        self.assertIn(
            "boom",
            result
            .issues[0]
            .message,
        )

    def test_invalid_availability_becomes_validation_issue(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementation = (
            InvalidAvailabilityImplementation(
                identifier="invalid-availability",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        "invalid-availability"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan,
                PipelineContext(),
            )
        )

        self.assertFalse(
            result.valid
        )

        self.assertIn(
            "invalid",
            result
            .issues[0]
            .message,
        )

    def test_raise_for_errors_raises_combined_error(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        plan = PipelinePlan(
            selections=(
                PipelineStageSelection(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        "missing-geometry"
                    ),
                ),
                PipelineStageSelection(
                    stage=(
                        PipelineStage.MATERIAL
                    ),
                    implementation_id=(
                        "missing-material"
                    ),
                ),
            )
        )

        result = (
            registry.validate_plan(
                plan
            )
        )

        with self.assertRaises(
            PipelineRegistryError
        ) as context:
            result.raise_for_errors()

        message = str(
            context.exception
        )

        self.assertIn(
            "missing-geometry",
            message,
        )

        self.assertIn(
            "missing-material",
            message,
        )


# ---------------------------------------------------------
# Default plan
# ---------------------------------------------------------

class DefaultPlanTests(
    unittest.TestCase
):
    def test_default_plan_uses_stage_defaults(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        input_impl = FakeImplementation(
            identifier="projection-images",
            stage=(
                PipelineStage.INPUT
            ),
        )

        geometry = geometry_impl(
            "native-hull"
        )

        material = material_impl(
            "projected-color-v1.2"
        )

        registry.register(
            input_impl
        )

        registry.register(
            geometry
        )

        registry.register(
            material
        )

        plan = build_default_plan(
            registry
        )

        self.assertEqual(
            [
                (
                    selection.stage,
                    selection.implementation_id,
                )
                for selection
                in plan.selections
            ],
            [
                (
                    PipelineStage.INPUT,
                    "projection-images",
                ),
                (
                    PipelineStage.GEOMETRY,
                    "native-hull",
                ),
                (
                    PipelineStage.MATERIAL,
                    "projected-color-v1.2",
                ),
            ],
        )

    def test_default_plan_can_exclude_optional_stages(
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
            )
        )

        registry.register(
            geometry_impl(
                "native-hull"
            )
        )

        registry.register(
            material_impl(
                "projected-color-v1.2"
            )
        )

        registry.register(
            rig_impl(
                "auto-rig"
            )
        )

        registry.register(
            FakeImplementation(
                identifier="glb",
                stage=(
                    PipelineStage.EXPORT
                ),
            )
        )

        plan = build_default_plan(
            registry,
            include_optional=False,
        )

        self.assertEqual(
            [
                selection.stage
                for selection
                in plan.selections
            ],
            [
                PipelineStage.INPUT,
                PipelineStage.GEOMETRY,
            ],
        )

    def test_missing_stage_is_omitted_from_default_plan(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        registry.register(
            geometry_impl(
                "native-hull"
            )
        )

        plan = build_default_plan(
            registry
        )

        self.assertEqual(
            len(
                plan.selections
            ),
            1,
        )

        self.assertEqual(
            plan
            .selections[0]
            .stage,
            PipelineStage.GEOMETRY,
        )


# ---------------------------------------------------------
# Bulk registration
# ---------------------------------------------------------

class RegisterManyTests(
    unittest.TestCase
):
    def test_register_many_registers_all(
        self,
    ) -> None:
        registry = (
            PipelineRegistry()
        )

        implementations = [
            geometry_impl(
                "geometry-a"
            ),
            geometry_impl(
                "geometry-b"
            ),
            material_impl(
                "material-a"
            ),
        ]

        register_many(
            registry,
            implementations,
        )

        self.assertEqual(
            len(registry),
            3,
        )

        self.assertEqual(
            registry.implementation_ids(
                PipelineStage.GEOMETRY
            ),
            (
                "geometry-a",
                "geometry-b",
            ),
        )

        self.assertEqual(
            registry.implementation_ids(
                PipelineStage.MATERIAL
            ),
            (
                "material-a",
            ),
        )


# ---------------------------------------------------------
# Context forwarding
# ---------------------------------------------------------

class ContextTests(
    unittest.TestCase
):
    def test_availability_receives_context(
        self,
    ) -> None:
        class ContextAwareImplementation(
            FakeImplementation
        ):
            def availability(
                self,
                context: PipelineContext,
            ) -> ImplementationAvailability:
                if (
                    context
                    .metadata
                    .get(
                        "enabled"
                    )
                ):
                    return (
                        ImplementationAvailability
                        .ready_state()
                    )

                return (
                    ImplementationAvailability
                    .unavailable(
                        "Context flag missing."
                    )
                )

        registry = (
            PipelineRegistry()
        )

        implementation = (
            ContextAwareImplementation(
                identifier="context-aware",
                stage=(
                    PipelineStage.GEOMETRY
                ),
            )
        )

        registry.register(
            implementation
        )

        unavailable = (
            registry.availability(
                "context-aware",
                PipelineContext(),
            )
        )

        ready = (
            registry.availability(
                "context-aware",
                PipelineContext(
                    metadata={
                        "enabled": True
                    }
                ),
            )
        )

        self.assertFalse(
            unavailable.available
        )

        self.assertTrue(
            ready.available
        )


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------

if __name__ == "__main__":
    unittest.main()