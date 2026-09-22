from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class PreflightTests(unittest.TestCase):

    def test_complete_plan_passes_preflight(self) -> None:
        registry, *_ = full_registry()
        runner = PipelineRunner(registry)
        issues = runner.preflight(full_plan(), PipelineContext())
        self.assertEqual(issues, ())

    def test_missing_input_stage_is_reported(self) -> None:
        registry = PipelineRegistry()
        registry.register(GeometryImplementation())
        plan = PipelinePlan(selections=(selection(PipelineStage.GEOMETRY, 'native-hull'),))
        issues = PipelineRunner(registry).preflight(plan, PipelineContext())
        self.assertTrue(any((issue.stage == PipelineStage.INPUT for issue in issues)))

    def test_missing_geometry_stage_is_reported(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        plan = PipelinePlan(selections=(selection(PipelineStage.INPUT, 'projection-images'),))
        issues = PipelineRunner(registry).preflight(plan, PipelineContext())
        self.assertTrue(any((issue.stage == PipelineStage.GEOMETRY for issue in issues)))

    def test_existing_input_output_satisfies_required_stage(self) -> None:
        registry = PipelineRegistry()
        registry.register(GeometryImplementation())
        plan = PipelinePlan(selections=(selection(PipelineStage.GEOMETRY, 'native-hull'),))
        context = PipelineContext()
        context.set_output(PipelineStage.INPUT, 'existing-input')
        issues = PipelineRunner(registry).preflight(plan, context)
        self.assertEqual(issues, ())

    def test_existing_geometry_output_allows_material_only_plan(self) -> None:
        registry = PipelineRegistry()
        registry.register(MaterialImplementation())
        plan = PipelinePlan(selections=(selection(PipelineStage.MATERIAL, 'projected-color-v1.2'),))
        context = PipelineContext()
        context.set_output(PipelineStage.INPUT, 'input')
        context.set_output(PipelineStage.GEOMETRY, 'geometry')
        issues = PipelineRunner(registry).preflight(plan, context)
        self.assertEqual(issues, ())

    def test_disabled_required_stage_is_reported(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        registry.register(GeometryImplementation())
        plan = PipelinePlan(selections=(selection(PipelineStage.INPUT, 'projection-images', enabled=False), selection(PipelineStage.GEOMETRY, 'native-hull')))
        issues = PipelineRunner(registry).preflight(plan, PipelineContext())
        self.assertTrue(any((issue.stage == PipelineStage.INPUT for issue in issues)))

    def test_unknown_implementation_is_reported(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        plan = PipelinePlan(selections=(selection(PipelineStage.INPUT, 'projection-images'), selection(PipelineStage.GEOMETRY, 'missing-geometry')))
        issues = PipelineRunner(registry).preflight(plan, PipelineContext())
        self.assertTrue(any((issue.implementation_id == 'missing-geometry' for issue in issues)))
