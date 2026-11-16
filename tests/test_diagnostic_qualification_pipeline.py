"""Replay actual immutable host-tool bytes and enforce the delivery gate."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.diagnostic_qualification.archive import verify_archive
from scripts.diagnostic_qualification.runner import ARCHIVE, run_evidence, review_template
from scripts.diagnostic_qualification.review import import_review
from scripts.qualify_diagnostic_evidence import main


class RealArchiveReplayTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_actual_tool_grid_violation_is_retained_without_repair_or_cost_inference(self):
        packet = verify_archive(ARCHIVE)
        with patch("scripts.diagnostic_qualification.corpora.run_corpora", side_effect=AssertionError("No matrix in verify-only mode")):
            result = run_evidence(self.root, verify_only=True)
        report = result["report"]
        self.assertEqual(report["technical_status"], "completed")
        self.assertEqual(report["comparison"]["reason"], "image_grid_changed")
        self.assertEqual(report["comparison"]["assets"]["after"]["width"], 1254)
        self.assertEqual(report["comparison"]["assets"]["before"]["width"], 1024)
        self.assertEqual(report["qualification_status"], "fail")
        self.assertEqual(report["attempt"]["execution"]["cost"], {"status": "unknown", "amount": None, "currency": None})
        self.assertIsNone(report["attempt"]["execution"]["backend_model"])
        self.assertEqual(verify_archive(ARCHIVE)["packet_sha256"], packet["packet_sha256"])
        page = (result["run_path"] / "review.html").read_text(encoding="utf-8")
        self.assertIn(packet["packet_sha256"], page)
        self.assertTrue((result["run_path"] / "reference_glb.glb").is_file())

    def test_completed_replay_is_distinct_from_a_qualified_delivery_exit_code(self):
        with redirect_stdout(StringIO()):
            normal = main(["--verify-only", "--output", str(self.root)])
            gate = main(["--verify-only", "--require-qualified-delivery", "--output", str(self.root)])
        self.assertEqual(normal, 0)
        self.assertEqual(gate, 1)
        self.assertEqual(len(list((self.root / "runs").iterdir())), 2)

    def test_page_template_does_not_invent_a_completed_human_attestation(self):
        packet = verify_archive(ARCHIVE)
        pending = review_template(packet)
        source = self.root / "pending.json"
        source.write_text(json.dumps(pending), encoding="utf-8")
        result = import_review(source, ARCHIVE, self.root / "review")
        self.assertEqual(result["human_review_status"], "unknown")
        self.assertEqual(result["delivery_status"], "unknown")
        self.assertFalse(result["reviewer"]["attested"])


if __name__ == "__main__":
    unittest.main()
