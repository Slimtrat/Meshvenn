from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class OrderingTests(unittest.TestCase):

    def test_entries_are_grouped_in_pipeline_order(self) -> None:
        registry = PipelineRegistry()
        registry.register(rig_impl('rig-a'))
        registry.register(material_impl('material-a'))
        registry.register(geometry_impl('geometry-a'))
        stages = [entry.descriptor.stage for entry in registry.entries()]
        self.assertEqual(stages, [PipelineStage.GEOMETRY, PipelineStage.MATERIAL, PipelineStage.RIG])

    def test_registration_order_is_preserved_inside_stage(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-c'))
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'))
        self.assertEqual(registry.implementation_ids(PipelineStage.GEOMETRY), ('geometry-c', 'geometry-a', 'geometry-b'))

    def test_iteration_yields_implementations(self) -> None:
        registry = PipelineRegistry()
        geometry = geometry_impl('geometry-a')
        material = material_impl('material-a')
        registry.register(material)
        registry.register(geometry)
        self.assertEqual(list(registry), [geometry, material])
