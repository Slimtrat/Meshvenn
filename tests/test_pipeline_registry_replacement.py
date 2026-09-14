from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class ReplacementTests(unittest.TestCase):

    def test_replace_updates_instance(self) -> None:
        registry = PipelineRegistry()
        original = geometry_impl('native-hull', label='Original')
        replacement = geometry_impl('native-hull', label='Reloaded')
        registry.register(original)
        registry.register(replacement, replace=True)
        self.assertIs(registry.get('native-hull'), replacement)
        self.assertEqual(registry.require_entry('native-hull').descriptor.label, 'Reloaded')

    def test_replace_preserves_registration_position(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'))
        replacement = geometry_impl('geometry-a', label='Reloaded A')
        registry.register(replacement, replace=True)
        self.assertEqual(registry.implementation_ids(PipelineStage.GEOMETRY), ('geometry-a', 'geometry-b'))

    def test_replace_preserves_default(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'))
        registry.register(geometry_impl('geometry-a'), replace=True)
        self.assertEqual(registry.default_id(PipelineStage.GEOMETRY), 'geometry-a')

    def test_replace_can_make_existing_implementation_default(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'))
        registry.register(geometry_impl('geometry-b'), replace=True, default=True)
        self.assertEqual(registry.default_id(PipelineStage.GEOMETRY), 'geometry-b')

    def test_replace_cannot_change_stage(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('shared-id'))
        incompatible = material_impl('shared-id')
        with self.assertRaises(StageMismatchError):
            registry.register(incompatible, replace=True)
