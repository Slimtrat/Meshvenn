"""A real execution error must survive corpus annotation and D7 aggregation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.appearance_diagnostics import AppearancePolicy
from core.diagnostic_contracts import CameraDeclaration, ContentReference, DiagnosticReport, ViewRevision, ViewSetRevision
from core.geometry_diagnostics import GeometryPolicy
from scripts.appearance_diagnostic_corpus import runner as appearance
from scripts.geometry_diagnostic_corpus import runner as geometry
from scripts.diagnostic_qualification.runner import run_evidence


class FailureEvidenceTests(unittest.TestCase):
    def test_failed_d3_d4_reports_keep_original_error_without_duplicate_engine_ids(self):
        image = ContentReference("a" * 64, 32, 32, "image/png")
        view = ViewRevision("front", 1, image, None, CameraDeclaration("orthographic", 0, 0))
        views = ViewSetRevision("failure-evidence", 1, (view,))
        error = {"error_type": "OSError", "message": "An original output could not be written."}
        reports = ((geometry, geometry.execution_failure_report(views, GeometryPolicy(), error), "geometry-corpus"),
                   (appearance, appearance.failure_report(views, 32, AppearancePolicy(), error), "appearance-corpus"))
        for runner, original, engine_id in reports:
            annotated = runner.complete_report(original, "b" * 64, {})
            self.assertEqual(annotated.completion, "failed")
            self.assertEqual(sum(e.engine_id == engine_id for e in annotated.engines), 1)
            self.assertTrue(any(error["message"] in (f.reason or "") for f in annotated.findings))
            self.assertEqual(DiagnosticReport.from_json(annotated.to_json()), annotated)

    def test_unavailable_quality_after_runner_failure_is_still_technical_failure(self):
        failed = {"status": "unknown", "all_full_matrices_passed": False,
                  "results": [{"id": "D3", "technical_status": "failed"}]}
        with tempfile.TemporaryDirectory() as folder:
            with patch("scripts.diagnostic_qualification.corpora.run_corpora", return_value=failed):
                result = run_evidence(Path(folder))
        self.assertEqual(result["report"]["technical_status"], "failed")


if __name__ == "__main__":
    unittest.main()
