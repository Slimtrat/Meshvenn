"""Reject stale geometry/fidelity and retain failures instead of visual approval."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.character_quality.assessment import assess_rendered
from scripts.character_quality.workflow import qualify_characters
from scripts.diagnostic_qualification.integrity import file_record, sha256_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/diagnostics/provider-v1/original-reference.glb"


def rendered(root):
    (root / "source.glb").write_bytes(SOURCE.read_bytes())
    digest = sha256_file(SOURCE)
    # A small closed mesh makes receipt-binding tests independent of Blender.
    mesh = {"source_glb_sha256": digest, "vertices": [[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
            "triangles": [[0,2,1],[0,1,3],[0,3,2],[1,2,3]]}
    (root / "mesh.json").write_text(json.dumps(mesh))
    assets = [{"asset_id": name, "role": role, "label": name,
               "glb": file_record(root / "source.glb", root),
               "mesh": file_record(root / "mesh.json", root),
               "reload": {"verified": True, "source_glb_sha256": digest}}
              for name, role in (("source", "source"), ("candidate", "candidate"))]
    return {"output_root": str(root), "status": "completed", "request_sha256": "1"*64, "assets": assets}


def fidelity(manifest):
    source, candidate = manifest["assets"]
    return {"status": "completed", "source": {"glb_sha256": source["glb"]["sha256"],
            "mesh_sha256": source["mesh"]["sha256"]}, "shared_frame": {"candidate_fit": False},
            "assets": [{"asset_id": candidate["asset_id"], "glb_sha256": candidate["glb"]["sha256"],
                        "mesh_sha256": candidate["mesh"]["sha256"], "gates": {}}]}


class AssessmentBindingTests(unittest.TestCase):
    def test_stale_fidelity_and_missing_candidates_fail_before_measurement(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = rendered(Path(temporary))
            original = fidelity(manifest)
            mutations = [lambda f: f.update(status="partial"),
                         lambda f: f["source"].update(glb_sha256="0"*64),
                         lambda f: f["source"].update(mesh_sha256="0"*64),
                         lambda f: f["shared_frame"].update(candidate_fit=True),
                         lambda f: f.update(assets=[]),
                         lambda f: f["assets"].append(deepcopy(f["assets"][0])),
                         lambda f: f["assets"][0].update(glb_sha256="0"*64),
                         lambda f: f["assets"][0].update(mesh_sha256="0"*64)]
            for mutate in mutations:
                changed = deepcopy(original); mutate(changed)
                with patch("scripts.character_quality.assessment.mesh_quality") as measure:
                    with self.assertRaises(ValueError):
                        assess_rendered(manifest, fidelity=changed)
                    measure.assert_not_called()

    def test_changed_vertices_and_reload_bound_to_another_glb_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); manifest = rendered(root)
            changed = deepcopy(manifest)
            changed["assets"][0]["reload"]["source_glb_sha256"] = "0"*64
            with self.assertRaises(ValueError):
                assess_rendered(changed)
            (root / "mesh.json").write_text("{}")
            with self.assertRaises(ValueError):
                assess_rendered(manifest)

    def test_same_mesh_without_human_evidence_never_certifies_a_character(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = rendered(Path(temporary))
            authority = {"frame_id": "fixture-frame", "regions": [], "sections": [], "authority_status": "unknown"}
            with patch("scripts.character_quality.assessment.source_authority", return_value=authority):
                result = assess_rendered(manifest, fidelity=fidelity(manifest))
            self.assertEqual(result["quality_certification"], "unknown")
            self.assertEqual(result["human_review"], "unknown")
            self.assertEqual(result["candidates"][0]["comparison"]["preservation_status"], "unknown")
            self.assertEqual(result["candidates"][0]["delivery"]["animated_use"], "unknown")


class WorkflowFailureTests(unittest.TestCase):
    def test_existing_results_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "review"; output.mkdir()
            sentinel = output / "qualification.json"; sentinel.write_text("original evidence")
            with self.assertRaises(FileExistsError):
                qualify_characters(output, blender_executable=SOURCE)
            self.assertEqual(sentinel.read_text(), "original evidence")

    def test_failed_native_worker_keeps_error_and_logs_without_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "review"
            def fail(*args, **kwargs):
                (output / "reconstruction-64.stderr.log").write_text("worker failed")
                raise ValueError("native worker failed")
            with patch("scripts.character_quality.workflow._reconstruct", side_effect=fail):
                with self.assertRaisesRegex(ValueError, "native worker failed"):
                    qualify_characters(output, blender_executable=SOURCE, native_library=SOURCE)
            result = json.loads((output / "qualification.json").read_text())
            self.assertEqual(result["technical_status"], "failed")
            self.assertEqual(result["quality_certification"], "unknown")
            self.assertEqual(result["stages"], [])
            self.assertEqual((output / "reconstruction-64.stderr.log").read_text(), "worker failed")
            self.assertFalse((output / "review/index.html").exists())


if __name__ == "__main__":
    unittest.main()
