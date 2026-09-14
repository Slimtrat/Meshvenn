from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class ClearTests(unittest.TestCase):

    def test_clear_resets_registry(self) -> None:
        registry = PipelineRegistry()
        registry.register(geometry_impl('geometry-a'))
        registry.register(material_impl('material-a'))
        registry.clear()
        self.assertEqual(len(registry), 0)
        self.assertEqual(registry.entries(), ())
        self.assertIsNone(registry.default_id(PipelineStage.GEOMETRY))
        self.assertIsNone(registry.default_id(PipelineStage.MATERIAL))
