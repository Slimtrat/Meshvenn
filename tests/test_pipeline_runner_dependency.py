from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class DependencyTests(unittest.TestCase):

    def test_material_only_can_use_existing_geometry(self) -> None:
        registry = PipelineRegistry()
        material = MaterialImplementation()
        registry.register(material)
        context = PipelineContext()
        context.set_output(PipelineStage.INPUT, 'existing-input')
        context.set_output(PipelineStage.GEOMETRY, 'existing-mesh')
        plan = PipelinePlan(selections=(selection(PipelineStage.MATERIAL, 'projected-color-v1.2'),))
        report = PipelineRunner(registry).run(plan, context)
        self.assertTrue(report.success)
        self.assertEqual(material.execute_calls, 1)
        self.assertEqual(context.get_output(PipelineStage.GEOMETRY), 'existing-mesh')

    def test_missing_runtime_dependency_fails_stage(self) -> None:
        registry = PipelineRegistry()
        material = MaterialImplementation()
        registry.register(material)
        context = PipelineContext()
        context.set_output(PipelineStage.INPUT, 'input')
        context.set_output(PipelineStage.GEOMETRY, 'mesh')
        plan = PipelinePlan(selections=(selection(PipelineStage.MATERIAL, 'projected-color-v1.2'),))
        runner = PipelineRunner(registry)
        self.assertEqual(runner.preflight(plan, context), ())
        context.outputs.pop(PipelineStage.GEOMETRY)
        record = runner._run_selection(plan.selections[0], context, PipelineRunOptions())
        self.assertTrue(record.failed)
        self.assertIn('geometry', record.result.message)
        self.assertEqual(material.execute_calls, 0)
