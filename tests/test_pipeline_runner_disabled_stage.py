from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class DisabledStageTests(unittest.TestCase):

    def test_disabled_optional_stage_is_skipped(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        registry.register(GeometryImplementation())
        material = MaterialImplementation()
        registry.register(material)
        plan = PipelinePlan(selections=(selection(PipelineStage.INPUT, 'projection-images'), selection(PipelineStage.GEOMETRY, 'native-hull'), selection(PipelineStage.MATERIAL, 'projected-color-v1.2', enabled=False)))
        report = PipelineRunner(registry).run(plan, PipelineContext())
        self.assertTrue(report.success)
        material_record = report.record_for(PipelineStage.MATERIAL)
        self.assertIsNotNone(material_record)
        self.assertTrue(material_record.skipped)
        self.assertEqual(material.execute_calls, 0)
