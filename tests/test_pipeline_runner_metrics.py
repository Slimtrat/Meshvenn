from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class MetricsTests(unittest.TestCase):

    def test_metrics_are_preserved(self) -> None:
        registry = PipelineRegistry()
        registry.register(FakeImplementation(identifier='projection-images', stage=PipelineStage.INPUT, payload='input', metrics={'views': 10}, metadata={'source': 'sheet'}))
        registry.register(GeometryImplementation())
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        record = report.record_for(PipelineStage.INPUT)
        self.assertEqual(record.result.metrics['views'], 10)
        self.assertEqual(record.result.metadata['source'], 'sheet')
