from __future__ import annotations

from tests.pipeline_registry_test_support import *  # noqa: F403

class LookupTests(unittest.TestCase):

    def test_require_returns_registered_implementation(self) -> None:
        registry = PipelineRegistry()
        implementation = material_impl('projected-color-v1.2')
        registry.register(implementation)
        self.assertIs(registry.require('projected-color-v1.2'), implementation)

    def test_require_unknown_raises(self) -> None:
        registry = PipelineRegistry()
        with self.assertRaises(UnknownImplementationError):
            registry.require('unknown')

    def test_require_can_validate_stage(self) -> None:
        registry = PipelineRegistry()
        implementation = material_impl('projected-color-v1.2')
        registry.register(implementation)
        self.assertIs(registry.require('projected-color-v1.2', stage=PipelineStage.MATERIAL), implementation)

    def test_require_wrong_stage_raises(self) -> None:
        registry = PipelineRegistry()
        registry.register(material_impl('projected-color-v1.2'))
        with self.assertRaises(StageMismatchError):
            registry.require('projected-color-v1.2', stage=PipelineStage.GEOMETRY)
