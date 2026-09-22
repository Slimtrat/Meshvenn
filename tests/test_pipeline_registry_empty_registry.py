from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class EmptyRegistryTests(unittest.TestCase):

    def test_new_registry_is_empty(self) -> None:
        registry = PipelineRegistry()
        self.assertEqual(len(registry), 0)
        self.assertFalse(registry)
        self.assertEqual(registry.entries(), ())

    def test_stage_has_no_implementations(self) -> None:
        registry = PipelineRegistry()
        self.assertFalse(registry.has_stage(PipelineStage.GEOMETRY))
        self.assertIsNone(registry.default_id(PipelineStage.GEOMETRY))
        self.assertIsNone(registry.default(PipelineStage.GEOMETRY))
