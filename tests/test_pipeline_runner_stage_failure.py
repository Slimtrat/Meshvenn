from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class StageFailureTests(unittest.TestCase):

    def test_failed_result_stops_pipeline_by_default(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        geometry = FakeImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY, result_state=StageResultState.FAILED, message='Geometry failed.')
        material = MaterialImplementation()
        registry.register(geometry)
        registry.register(material)
        plan = PipelinePlan(selections=(selection(PipelineStage.INPUT, 'projection-images'), selection(PipelineStage.GEOMETRY, 'native-hull'), selection(PipelineStage.MATERIAL, 'projected-color-v1.2')))
        report = PipelineRunner(registry).run(plan, PipelineContext())
        self.assertTrue(report.failed)
        self.assertTrue(report.aborted)
        self.assertEqual(geometry.execute_calls, 1)
        self.assertEqual(material.execute_calls, 0)

    def test_stop_on_failure_false_attempts_later_stages(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        geometry = FakeImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY, result_state=StageResultState.FAILED, message='Geometry failed.')
        material = MaterialImplementation()
        registry.register(geometry)
        registry.register(material)
        plan = PipelinePlan(selections=(selection(PipelineStage.INPUT, 'projection-images'), selection(PipelineStage.GEOMETRY, 'native-hull'), selection(PipelineStage.MATERIAL, 'projected-color-v1.2')))
        report = PipelineRunner(registry).run(plan, PipelineContext(), options=PipelineRunOptions(stop_on_failure=False))
        self.assertTrue(report.failed)
        self.assertFalse(report.aborted)
        material_record = report.record_for(PipelineStage.MATERIAL)
        self.assertIsNotNone(material_record)
        self.assertTrue(material_record.failed)
        self.assertEqual(material.execute_calls, 0)
