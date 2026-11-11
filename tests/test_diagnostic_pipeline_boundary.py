from __future__ import annotations

import unittest

from core.diagnostic_contracts import VerificationStatus
from core.pipeline_contracts import PipelineContext, PipelineStage, StageExecutionResult
from core.pipeline_runner import PipelineRunner
from tests.diagnostic_contracts_test_support import report
from tests.pipeline_runner_test_support import full_plan, full_registry


class DiagnosticResultBoundaryTests(unittest.TestCase):
    def test_successful_stage_carries_unknown_diagnostic_without_certifying_asset(self):
        registry, input_impl, geometry, material, rig, exporter = full_registry()
        diagnostic = report(completion="partial")
        payload = geometry.payload
        geometry.execute = lambda context: StageExecutionResult.succeeded(
            stage=PipelineStage.GEOMETRY, implementation_id="native-hull", payload=payload,
            diagnostic_report=diagnostic)
        execution = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        self.assertTrue(execution.success)
        self.assertIs(execution.context.get_output(PipelineStage.GEOMETRY), payload)
        self.assertIs(execution.diagnostic_report_for(PipelineStage.GEOMETRY), diagnostic)
        self.assertEqual(diagnostic.verification_status, VerificationStatus.UNKNOWN)
        self.assertIsNone(execution.diagnostic_report_for(PipelineStage.MATERIAL))

    def test_result_boundary_creates_reads_and_rejects_invalid_json(self):
        original = StageExecutionResult.failed_result(stage=PipelineStage.GEOMETRY, implementation_id="native-hull", message="Engine failed.")
        self.assertIsNone(original.diagnostic_report_json())
        attached = original.with_diagnostic_report(report(completion="failed"))
        restored = original.with_diagnostic_report_json(attached.diagnostic_report_json())
        self.assertEqual(restored.diagnostic_report, attached.diagnostic_report)
        self.assertTrue(restored.failed)
        self.assertIsNone(original.diagnostic_report)
        with self.assertRaises(ValueError):
            original.with_diagnostic_report_json('{"schema_version":99}')
        with self.assertRaises(TypeError):
            original.with_diagnostic_report({"schema_version": 1})


if __name__ == "__main__":
    unittest.main()
