from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class TimingTests(unittest.TestCase):

    def test_stage_duration_is_non_negative(self) -> None:
        registry, *_ = full_registry()
        report = PipelineRunner(registry).run(full_plan(), PipelineContext())
        for record in report.records:
            self.assertGreaterEqual(record.duration_seconds, 0.0)

    def test_total_duration_is_non_negative(self) -> None:
        registry, *_ = full_registry()
        report = PipelineRunner(registry).run(full_plan(), PipelineContext())
        self.assertGreaterEqual(report.duration_seconds, 0.0)
