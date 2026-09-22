from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class ReportTests(unittest.TestCase):

    def test_record_for_unknown_stage_returns_none(self) -> None:
        report = PipelineExecutionReport(plan=PipelinePlan(selections=()), context=PipelineContext(), records=(), issues=(), duration_seconds=0.0, aborted=False)
        self.assertIsNone(report.record_for(PipelineStage.RIG))
        self.assertIsNone(report.result_for(PipelineStage.RIG))

    def test_failure_message_contains_stage_and_implementation(self) -> None:
        selected = selection(PipelineStage.GEOMETRY, 'native-hull')
        record = StageRunRecord(selection=selected, result=StageExecutionResult.failed_result(stage=PipelineStage.GEOMETRY, implementation_id='native-hull', message='No mesh.'), duration_seconds=0.0)
        report = PipelineExecutionReport(plan=PipelinePlan(selections=(selected,)), context=PipelineContext(), records=(record,), issues=(), duration_seconds=0.0, aborted=True)
        self.assertIn('geometry', report.failure_message)
        self.assertIn('native-hull', report.failure_message)
        self.assertIn('No mesh.', report.failure_message)

    def test_failure_message_contains_preflight_issue(self) -> None:
        report = PipelineExecutionReport(plan=PipelinePlan(selections=()), context=PipelineContext(), records=(), issues=(PipelineRunIssue(stage=PipelineStage.INPUT, implementation_id=None, message='Missing input.'),), duration_seconds=0.0, aborted=True)
        self.assertIn('Missing input.', report.failure_message)

    def test_raise_for_failure_does_nothing_for_success(self) -> None:
        report = PipelineExecutionReport(plan=PipelinePlan(selections=()), context=PipelineContext(), records=(), issues=(), duration_seconds=0.0, aborted=False)
        report.raise_for_failure()

    def test_raise_for_failure_raises_report_error(self) -> None:
        report = PipelineExecutionReport(plan=PipelinePlan(selections=()), context=PipelineContext(), records=(), issues=(PipelineRunIssue(stage=None, implementation_id=None, message='Broken pipeline.'),), duration_seconds=0.0, aborted=True)
        with self.assertRaises(PipelineExecutionError) as error:
            report.raise_for_failure()
        self.assertIs(error.exception.report, report)
