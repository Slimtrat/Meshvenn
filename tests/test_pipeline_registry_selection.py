from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class SelectionTests(unittest.TestCase):

    def test_resolve_selection_returns_implementation(self) -> None:
        registry = PipelineRegistry()
        implementation = material_impl('projected-color-v1.2')
        registry.register(implementation)
        selection = PipelineStageSelection(stage=PipelineStage.MATERIAL, implementation_id='projected-color-v1.2')
        self.assertIs(registry.resolve_selection(selection), implementation)

    def test_resolve_selection_rejects_stage_mismatch(self) -> None:
        registry = PipelineRegistry()
        registry.register(material_impl('projected-color-v1.2'))
        selection = PipelineStageSelection(stage=PipelineStage.GEOMETRY, implementation_id='projected-color-v1.2')
        with self.assertRaises(StageMismatchError):
            registry.resolve_selection(selection)
