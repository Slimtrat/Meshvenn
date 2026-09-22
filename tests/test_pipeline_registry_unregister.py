from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class UnregisterTests(unittest.TestCase):

    def test_unregister_removes_implementation(self) -> None:
        registry = PipelineRegistry()
        implementation = geometry_impl()
        registry.register(implementation)
        removed = registry.unregister('geometry-a')
        self.assertIs(removed, implementation)
        self.assertNotIn('geometry-a', registry)

    def test_unregister_unknown_returns_none(self) -> None:
        registry = PipelineRegistry()
        self.assertIsNone(registry.unregister('unknown'))

    def test_removing_default_promotes_first_remaining(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'))
        registry.register(geometry_impl('geometry-c'))
        registry.unregister('geometry-a')
        self.assertEqual(registry.default_id(PipelineStage.GEOMETRY), 'geometry-b')

    def test_removing_last_default_leaves_stage_without_default(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.unregister('geometry-a')
        self.assertIsNone(registry.default_id(PipelineStage.GEOMETRY))
        self.assertFalse(registry.has_stage(PipelineStage.GEOMETRY))
