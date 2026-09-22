from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class AvailabilityTests(unittest.TestCase):

    def test_ready_implementation_is_available(self) -> None:
        registry = PipelineRegistry()
        implementation = geometry_impl('native-hull')
        registry.register(implementation)
        availability = registry.availability('native-hull', PipelineContext())
        self.assertTrue(availability.available)
        self.assertTrue(availability.ready)
        self.assertEqual(availability.state, AvailabilityState.READY)

    def test_degraded_implementation_is_still_available(self) -> None:
        registry = PipelineRegistry()
        implementation = geometry_impl('degraded', availability=ImplementationAvailability.degraded('Fallback backend active.'))
        registry.register(implementation)
        availability = registry.availability('degraded', PipelineContext())
        self.assertTrue(availability.available)
        self.assertFalse(availability.ready)

    def test_unavailable_implementation_is_not_available(self) -> None:
        registry = PipelineRegistry()
        implementation = rig_impl('auto-rig', availability=ImplementationAvailability.unavailable('Not implemented yet.'))
        registry.register(implementation)
        availability = registry.availability('auto-rig', PipelineContext())
        self.assertFalse(availability.available)
        self.assertEqual(availability.reason, 'Not implemented yet.')

    def test_availability_entries_include_default_flag(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(geometry_impl('geometry-b'))
        entries = registry.availability_entries(PipelineStage.GEOMETRY, PipelineContext())
        self.assertEqual(len(entries), 2)
        self.assertTrue(entries[0].is_default)
        self.assertFalse(entries[1].is_default)

    def test_available_entries_filter_unavailable(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('ready'))
        registry.register(geometry_impl('offline', availability=ImplementationAvailability.unavailable('Offline.')))
        entries = registry.available_entries(PipelineStage.GEOMETRY, PipelineContext())
        self.assertEqual([entry.identifier for entry in entries], ['ready'])

    def test_invalid_availability_result_is_rejected(self) -> None:
        registry = PipelineRegistry()
        implementation = InvalidAvailabilityImplementation(identifier='invalid', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        with self.assertRaises(InvalidImplementationError):
            registry.availability('invalid', PipelineContext())
