from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class DefaultTests(unittest.TestCase):

    def test_set_default_switches_default(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'))
        registry.set_default(PipelineStage.GEOMETRY, 'geometry-b')
        self.assertEqual(registry.default_id(PipelineStage.GEOMETRY), 'geometry-b')

    def test_set_default_rejects_wrong_stage(self) -> None:
        registry = PipelineRegistry()
        registry.register(material_impl('material-a'))
        with self.assertRaises(StageMismatchError):
            registry.set_default(PipelineStage.GEOMETRY, 'material-a')

    def test_resolve_stage_uses_default(self) -> None:
        registry = PipelineRegistry()
        implementation = geometry_impl('native-hull')
        registry.register(implementation)
        self.assertIs(registry.resolve_stage(PipelineStage.GEOMETRY), implementation)

    def test_resolve_stage_can_use_explicit_id(self) -> None:
        registry = PipelineRegistry()
        first = geometry_impl('geometry-a')
        second = geometry_impl('geometry-b')
        registry.register(first)
        registry.register(second)
        self.assertIs(registry.resolve_stage(PipelineStage.GEOMETRY, 'geometry-b'), second)

    def test_resolve_stage_without_implementation_raises(self) -> None:
        registry = PipelineRegistry()
        with self.assertRaises(UnknownImplementationError):
            registry.resolve_stage(PipelineStage.RIG)
