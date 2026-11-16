"""Complete regression matrices and missing product proof cannot collapse into success."""
import unittest

from scripts.diagnostic_qualification.report import assemble_report


class QualificationClaimTests(unittest.TestCase):
    def test_five_passed_regression_suites_do_not_certify_provider_or_export(self):
        result = assemble_report({"status": "pass", "all_full_matrices_passed": True},
                                 attempt={"packet_sha256": "a" * 64},
                                 comparison={"outside_pixels_status": "pass"},
                                 reference={"status": "pass"}, review={"human_review_status": "pass"})
        self.assertEqual(result["qualification_status"], "unknown")
        statuses = {c["id"]: c["status"] for c in result["checks"]}
        self.assertEqual(statuses["frozen_regressions"], "pass")
        self.assertEqual(statuses["corrected_glb_delivery"], "unknown")
        self.assertEqual(statuses["semantic_identity"], "unknown")

    def test_deletion_or_regridding_is_not_hidden_by_passed_regressions(self):
        for comparison in ({"outside_pixels_status": "fail"}, {"reason": "image_grid_changed"}):
            result = assemble_report({"status": "pass", "all_full_matrices_passed": True}, comparison=comparison)
            self.assertEqual(result["qualification_status"], "fail")

    def test_partial_matrix_and_missing_native_library_remain_unknown(self):
        result = assemble_report({"status": "pass", "all_full_matrices_passed": False})
        self.assertEqual(result["checks"][0]["status"], "unknown")
        self.assertEqual(result["qualification_status"], "unknown")
        failure = assemble_report({"status": "fail", "all_full_matrices_passed": False})
        self.assertEqual(failure["qualification_status"], "fail")


if __name__ == "__main__":
    unittest.main()
