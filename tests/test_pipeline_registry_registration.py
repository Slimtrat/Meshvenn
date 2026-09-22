from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class RegistrationTests(unittest.TestCase):

    def test_register_adds_implementation(self) -> None:
        registry = PipelineRegistry()
        implementation = geometry_impl()
        returned = registry.register(implementation)
        self.assertIs(returned, implementation)
        self.assertEqual(len(registry), 1)
        self.assertIn('geometry-a', registry)
        self.assertIs(registry.get('geometry-a'), implementation)

    def test_first_implementation_becomes_default(self) -> None:
        registry = PipelineRegistry()
        implementation = geometry_impl('native-hull')
        registry.register(implementation, default=False)
        self.assertEqual(registry.default_id(PipelineStage.GEOMETRY), 'native-hull')
        self.assertIs(registry.default(PipelineStage.GEOMETRY), implementation)

    def test_second_implementation_does_not_replace_default(self) -> None:
        registry = PipelineRegistry()
        first = geometry_impl('geometry-a')
        second = geometry_impl('geometry-b')
        registry.register(first)
        registry.register(second)
        self.assertEqual(registry.default_id(PipelineStage.GEOMETRY), 'geometry-a')

    def test_explicit_default_replaces_previous_default(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'), default=True)
        self.assertEqual(registry.default_id(PipelineStage.GEOMETRY), 'geometry-b')
        entries = registry.entries(PipelineStage.GEOMETRY)
        defaults = [entry.descriptor.identifier for entry in entries if entry.is_default]
        self.assertEqual(defaults, ['geometry-b'])

    def test_duplicate_registration_is_rejected(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('same'))
        with self.assertRaises(DuplicateImplementationError):
            registry.register(geometry_impl('same'))

    def test_none_implementation_is_rejected(self) -> None:
        registry = PipelineRegistry()
        with self.assertRaises(InvalidImplementationError):
            registry.register(None)

    def test_missing_availability_is_rejected(self) -> None:
        registry = PipelineRegistry()
        with self.assertRaises(InvalidImplementationError):
            registry.register(MissingAvailabilityImplementation())

    def test_missing_execute_is_rejected(self) -> None:
        registry = PipelineRegistry()
        with self.assertRaises(InvalidImplementationError):
            registry.register(MissingExecuteImplementation())
