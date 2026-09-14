from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class ContextTests(unittest.TestCase):

    def test_availability_receives_context(self) -> None:

        class ContextAwareImplementation(FakeImplementation):

            def availability(self, context: PipelineContext) -> ImplementationAvailability:
                if context.metadata.get('enabled'):
                    return ImplementationAvailability.ready_state()
                return ImplementationAvailability.unavailable('Context flag missing.')
        registry = PipelineRegistry()
        implementation = ContextAwareImplementation(identifier='context-aware', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        unavailable = registry.availability('context-aware', PipelineContext())
        ready = registry.availability('context-aware', PipelineContext(metadata={'enabled': True}))
        self.assertFalse(unavailable.available)
        self.assertTrue(ready.available)
