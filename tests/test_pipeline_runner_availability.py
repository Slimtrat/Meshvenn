from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class AvailabilityTests(unittest.TestCase):

    def test_geometry_availability_is_checked_after_input(self) -> None:
        registry = PipelineRegistry()
        input_implementation = InputImplementation()
        geometry = GeometryImplementation()
        registry.register(input_implementation)
        registry.register(geometry)
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        self.assertTrue(report.success)
        self.assertEqual(geometry.availability_calls, 1)
        self.assertEqual(geometry.execute_calls, 1)

    def test_material_availability_can_depend_on_geometry_output(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        registry.register(GeometryImplementation())
        material = MaterialImplementation()
        registry.register(material)
        plan = PipelinePlan(selections=(selection(PipelineStage.INPUT, 'projection-images'), selection(PipelineStage.GEOMETRY, 'native-hull'), selection(PipelineStage.MATERIAL, 'projected-color-v1.2')))
        report = PipelineRunner(registry).run(plan, PipelineContext())
        self.assertTrue(report.success)
        self.assertEqual(material.execute_calls, 1)

    def test_unavailable_stage_fails_without_execution(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        unavailable_geometry = FakeImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY, availability=ImplementationAvailability.unavailable('Native library missing.'))
        registry.register(unavailable_geometry)
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        self.assertTrue(report.failed)
        self.assertTrue(report.aborted)
        self.assertEqual(unavailable_geometry.execute_calls, 0)
        geometry_record = report.record_for(PipelineStage.GEOMETRY)
        self.assertIsNotNone(geometry_record)
        self.assertTrue(geometry_record.failed)
        self.assertEqual(geometry_record.availability.state, AvailabilityState.UNAVAILABLE)

    def test_availability_check_can_be_disabled(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        implementation = FakeImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY, payload='geometry', availability=ImplementationAvailability.unavailable('Disabled backend.'))
        registry.register(implementation)
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext(), options=PipelineRunOptions(check_availability=False))
        self.assertTrue(report.success)
        self.assertEqual(implementation.availability_calls, 0)
        self.assertEqual(implementation.execute_calls, 1)
