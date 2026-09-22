from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class StageOrderingTests(unittest.TestCase):

    def test_plan_input_order_does_not_change_execution_order(self) -> None:
        registry, *_ = full_registry()
        plan = PipelinePlan(selections=(selection(PipelineStage.EXPORT, 'glb'), selection(PipelineStage.RIG, 'auto-rig'), selection(PipelineStage.MATERIAL, 'projected-color-v1.2'), selection(PipelineStage.GEOMETRY, 'native-hull'), selection(PipelineStage.INPUT, 'projection-images')))
        report = PipelineRunner(registry).run(plan, PipelineContext())
        self.assertTrue(report.success)
        self.assertEqual([record.stage for record in report.records], [PipelineStage.INPUT, PipelineStage.GEOMETRY, PipelineStage.MATERIAL, PipelineStage.RIG, PipelineStage.EXPORT])
