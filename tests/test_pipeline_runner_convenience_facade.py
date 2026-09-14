from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class ConvenienceFacadeTests(unittest.TestCase):

    def test_run_pipeline_wrapper_uses_registry(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        registry.register(GeometryImplementation())
        report = run_pipeline(registry, full_plan(material=False, rig=False, export=False), PipelineContext())
        self.assertTrue(report.success)
        self.assertEqual(len(report.records), 2)
