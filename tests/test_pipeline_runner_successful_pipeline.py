from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class SuccessfulPipelineTests(unittest.TestCase):

    def test_full_pipeline_runs_in_stage_order(self) -> None:
        registry, input_implementation, geometry, material, rig, exporter = full_registry()
        report = PipelineRunner(registry).run(full_plan(), PipelineContext())
        self.assertTrue(report.success)
        self.assertFalse(report.failed)
        self.assertFalse(report.aborted)
        self.assertEqual([record.stage for record in report.records], [PipelineStage.INPUT, PipelineStage.GEOMETRY, PipelineStage.MATERIAL, PipelineStage.RIG, PipelineStage.EXPORT])
        self.assertEqual(input_implementation.execute_calls, 1)
        self.assertEqual(geometry.execute_calls, 1)
        self.assertEqual(material.execute_calls, 1)
        self.assertEqual(rig.execute_calls, 1)
        self.assertEqual(exporter.execute_calls, 1)

    def test_outputs_propagate_between_stages(self) -> None:
        registry, *_ = full_registry()
        context = PipelineContext()
        report = PipelineRunner(registry).run(full_plan(), context)
        self.assertTrue(report.success)
        self.assertEqual(context.get_output(PipelineStage.INPUT), 'input-data')
        self.assertEqual(context.get_output(PipelineStage.GEOMETRY), 'geometry-data')
        self.assertEqual(context.get_output(PipelineStage.MATERIAL), 'material-data')
        self.assertEqual(context.get_output(PipelineStage.RIG), 'rig-data')
        self.assertEqual(context.get_output(PipelineStage.EXPORT), 'export-data')

    def test_same_context_is_used_by_all_stages(self) -> None:
        registry, input_implementation, geometry, material, rig, exporter = full_registry()
        context = PipelineContext()
        PipelineRunner(registry).run(full_plan(), context)
        for implementation in (input_implementation, geometry, material, rig, exporter):
            self.assertTrue(all((received is context for received in implementation.received_contexts)))

    def test_optional_stages_can_be_omitted(self) -> None:
        registry, *_ = full_registry()
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        self.assertTrue(report.success)
        self.assertEqual([record.stage for record in report.records], [PipelineStage.INPUT, PipelineStage.GEOMETRY])
