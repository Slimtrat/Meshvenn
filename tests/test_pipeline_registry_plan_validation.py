from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class PlanValidationTests(unittest.TestCase):

    def test_valid_plan_passes(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('native-hull'))
        registry.register(material_impl('projected-color-v1.2'))
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.GEOMETRY, implementation_id='native-hull'), PipelineStageSelection(stage=PipelineStage.MATERIAL, implementation_id='projected-color-v1.2')))
        result = registry.validate_plan(plan, PipelineContext())
        self.assertTrue(result.valid)
        self.assertEqual(result.issues, ())

    def test_unknown_implementation_is_reported(self) -> None:
        registry = PipelineRegistry()
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.GEOMETRY, implementation_id='missing-engine'),))
        result = registry.validate_plan(plan, PipelineContext())
        self.assertFalse(result.valid)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].implementation_id, 'missing-engine')

    def test_stage_mismatch_is_reported(self) -> None:
        registry = PipelineRegistry()
        registry.register(material_impl('projected-color-v1.2'))
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.GEOMETRY, implementation_id='projected-color-v1.2'),))
        result = registry.validate_plan(plan, PipelineContext())
        self.assertFalse(result.valid)
        self.assertIn('material', result.issues[0].message)

    def test_unavailable_implementation_is_reported(self) -> None:
        registry = PipelineRegistry()
        registry.register(rig_impl('auto-rig', availability=ImplementationAvailability.unavailable('Rig backend unavailable.')))
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.RIG, implementation_id='auto-rig'),))
        result = registry.validate_plan(plan, PipelineContext())
        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].message, 'Rig backend unavailable.')

    def test_disabled_selection_is_not_validated(self) -> None:
        registry = PipelineRegistry()
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.RIG, implementation_id='missing-rig', enabled=False),))
        result = registry.validate_plan(plan, PipelineContext())
        self.assertTrue(result.valid)

    def test_availability_can_be_skipped(self) -> None:
        registry = PipelineRegistry()
        registry.register(rig_impl('auto-rig', availability=ImplementationAvailability.unavailable('Not ready.')))
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.RIG, implementation_id='auto-rig'),))
        result = registry.validate_plan(plan, PipelineContext(), check_availability=False)
        self.assertTrue(result.valid)

    def test_availability_exception_becomes_validation_issue(self) -> None:
        registry = PipelineRegistry()
        implementation = ExplodingAvailabilityImplementation(identifier='exploding', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.GEOMETRY, implementation_id='exploding'),))
        result = registry.validate_plan(plan, PipelineContext())
        self.assertFalse(result.valid)
        self.assertIn('boom', result.issues[0].message)

    def test_invalid_availability_becomes_validation_issue(self) -> None:
        registry = PipelineRegistry()
        implementation = InvalidAvailabilityImplementation(identifier='invalid-availability', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.GEOMETRY, implementation_id='invalid-availability'),))
        result = registry.validate_plan(plan, PipelineContext())
        self.assertFalse(result.valid)
        self.assertIn('invalid', result.issues[0].message)

    def test_raise_for_errors_raises_combined_error(self) -> None:
        registry = PipelineRegistry()
        plan = PipelinePlan(selections=(PipelineStageSelection(stage=PipelineStage.GEOMETRY, implementation_id='missing-geometry'), PipelineStageSelection(stage=PipelineStage.MATERIAL, implementation_id='missing-material')))
        result = registry.validate_plan(plan)
        with self.assertRaises(PipelineRegistryError) as context:
            result.raise_for_errors()
        message = str(context.exception)
        self.assertIn('missing-geometry', message)
        self.assertIn('missing-material', message)
