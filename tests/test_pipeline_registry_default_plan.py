from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class DefaultPlanTests(unittest.TestCase):

    def test_default_plan_uses_stage_defaults(self) -> None:
        registry = PipelineRegistry()
        input_impl = FakeImplementation(identifier='projection-images', stage=PipelineStage.INPUT)
        geometry = geometry_impl('native-hull')
        material = material_impl('projected-color-v1.2')
        registry.register(input_impl)
        registry.register(geometry)
        registry.register(material)
        plan = build_default_plan(registry)
        self.assertEqual([(selection.stage, selection.implementation_id) for selection in plan.selections], [(PipelineStage.INPUT, 'projection-images'), (PipelineStage.GEOMETRY, 'native-hull'), (PipelineStage.MATERIAL, 'projected-color-v1.2')])

    def test_default_plan_can_exclude_optional_stages(self) -> None:
        registry = PipelineRegistry()
        registry.register(FakeImplementation(identifier='projection-images', stage=PipelineStage.INPUT))
        registry.register(geometry_impl('native-hull'))
        registry.register(material_impl('projected-color-v1.2'))
        registry.register(rig_impl('auto-rig'))
        registry.register(FakeImplementation(identifier='glb', stage=PipelineStage.EXPORT))
        plan = build_default_plan(registry, include_optional=False)
        self.assertEqual([selection.stage for selection in plan.selections], [PipelineStage.INPUT, PipelineStage.GEOMETRY])

    def test_missing_stage_is_omitted_from_default_plan(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('native-hull'))
        plan = build_default_plan(registry)
        self.assertEqual(len(plan.selections), 1)
        self.assertEqual(plan.selections[0].stage, PipelineStage.GEOMETRY)
