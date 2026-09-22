from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class StageRunRecordTests(unittest.TestCase):

    def test_properties_forward_result_state(self) -> None:
        selected = selection(PipelineStage.INPUT, 'projection-images')
        result = StageExecutionResult.succeeded(stage=PipelineStage.INPUT, implementation_id='projection-images')
        record = StageRunRecord(selection=selected, result=result, duration_seconds=0.1)
        self.assertEqual(record.stage, PipelineStage.INPUT)
        self.assertEqual(record.implementation_id, 'projection-images')
        self.assertTrue(record.success)
        self.assertFalse(record.failed)
        self.assertFalse(record.skipped)
