from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class RegisterManyTests(unittest.TestCase):

    def test_register_many_registers_all(self) -> None:
        registry = PipelineRegistry()
        implementations = [geometry_impl('geometry-a'), geometry_impl('geometry-b'), material_impl('material-a')]
        register_many(registry, implementations)
        self.assertEqual(len(registry), 3)
        self.assertEqual(registry.implementation_ids(PipelineStage.GEOMETRY), ('geometry-a', 'geometry-b'))
        self.assertEqual(registry.implementation_ids(PipelineStage.MATERIAL), ('material-a',))
