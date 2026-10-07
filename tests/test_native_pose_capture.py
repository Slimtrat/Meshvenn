"""Exact matrix projection, privacy boundary and synchronized-pose fixture."""
import copy
import hashlib
import json
import math
from pathlib import Path
import unittest

from core.native_pose_capture import CONVENTION, LAYOUT, REGIONS, project_capture, validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from scripts.extract_stytch_pose_series import SOURCE_BASE, SOURCE_BLOBS, verify_source_blob

FIXTURE = Path(__file__).resolve().parents[1] / "example/v2/poses/StytchDoll/complete"


def load(name):
    return json.loads((FIXTURE / name).read_text("utf-8"))


def captured():
    document = load("factory-held.json")
    proof = load("factory-held.matrices.json")
    return {"SchemaVersion": 1, "AssetSha256": document["AssetSha256"],
            "CoordinateFrame": document["CoordinateFrame"], "MatrixLayout": LAYOUT,
            "PoseConvention": CONVENTION, "CaptureFile": "held.png", "CaptureSha256": "a"*64,
            "Context": {"Consumer": "selected-factory", "Pose": "held", "Telemetry": "PRIVATE"},
            "Ancestors": [{"Name": "PRIVATE", **a} for a in proof["ancestors"]],
            "Mounts": [{"ModuleIds": ["PRIVATE"]}], "Controls": [{"Name": "PRIVATE"}],
            "Regions": [{"Id": name, "Visible": True} for name in sorted(REGIONS)],
            "Bones": [{**b, "RestRelative": proof["rest_relative"][b["Name"]],
                       "SkeletonSpace": proof["skeleton_space"][b["Name"]]} for b in document["Bones"]]}


class NativeCaptureTests(unittest.TestCase):
    def test_whitelist_preserves_exact_native_matrices_and_excludes_private_fields(self):
        document, proof, metadata = project_capture(captured())
        self.assertEqual(document, load("factory-held.json"))
        self.assertEqual(proof, load("factory-held.matrices.json"))
        self.assertNotIn("PRIVATE", json.dumps((document, proof, metadata)))
        self.assertNotIn("Telemetry", metadata["context"])
        self.assertEqual(set(document), {"AssetSha256", "CoordinateFrame", "Bones"})
        self.assertLess(max(metadata["matrix_recomposition"].values()), 2e-4)

    def test_corrupt_relative_skeleton_and_ancestor_composition_rejected(self):
        for kind in ("relative", "skeleton", "ancestor", "double-rest"):
            value = captured()
            if kind == "relative":
                value["Bones"][0]["RestRelative"][9] += .1
            elif kind == "skeleton":
                value["Bones"][5]["SkeletonSpace"][9] += .1
            elif kind == "ancestor":
                value["Ancestors"][0]["World"][9] += .1
            else:
                value["Bones"][1]["Pose"][10] += value["Bones"][1]["Rest"][10]
            with self.assertRaises(ValueError):
                project_capture(value)

    def test_invalid_schema_layout_fingerprint_and_png_path_fail_closed(self):
        for key, replacement in (("SchemaVersion", True), ("MatrixLayout", "rows"),
                                 ("PoseConvention", "delta"), ("AssetSha256", "wrong"),
                                 ("CaptureFile", "../private.png"), ("CaptureSha256", "wrong")):
            value = captured()
            value[key] = replacement
            with self.assertRaises(ValueError):
                project_capture(value)
        value = captured()
        value["Bones"][0]["Pose"][0] = math.nan
        with self.assertRaises(ValueError):
            project_capture(value)

    def test_visibility_and_nonfinite_provenance_cannot_be_laundered(self):
        for key, replacement in (("Visible", 1), ("Id", "unknown")):
            value = captured()
            value["Regions"][0][key] = replacement
            with self.assertRaises(ValueError):
                project_capture(value)
        value = captured()
        value["Regions"][0] = copy.deepcopy(value["Regions"][1])
        with self.assertRaises(ValueError):
            project_capture(value)
        value = captured()
        value["Context"]["CyclePhase"] = math.inf
        with self.assertRaises(ValueError):
            project_capture(value)

    def test_nineteen_pinned_matrices_recompose_and_have_exact_provenance(self):
        index = load("index.json")
        self.assertEqual(hashlib.sha256((FIXTURE / "index.json").read_bytes()).hexdigest(),
                         "5023701a1036067891bb961e527dc69d35e57973339ebad1c5e58d469d8e79c7")
        self.assertEqual(index["source_revision"], "1c9040e51be1e757c974eca794604cb9553cb532")
        self.assertEqual(index["source_repository"], "Stytch0/Stytch")
        self.assertEqual(index["case_count"], 19)
        self.assertEqual(len(index["cases"]), 19)
        self.assertEqual(len({c["id"] for c in index["cases"]}), 19)
        for case in index["cases"]:
            for key in ("probe", "matrix_proof"):
                self.assertEqual(hashlib.sha256((FIXTURE / case[key]).read_bytes()).hexdigest(), case[key+"_sha256"])
            probe = NativePoseProbe.from_dict(load(case["probe"]))
            self.assertEqual(probe.asset_sha256, index["asset_sha256"])
            self.assertEqual(validate_matrix_proof(probe, load(case["matrix_proof"])), case["matrix_recomposition"])
            self.assertEqual(len(case["source_json_sha256"]), 64)
            self.assertEqual(len(case["source_git_blob"]), 40)
            self.assertEqual(case["source_git_blob"], SOURCE_BLOBS[case["source_path"].removeprefix(SOURCE_BASE)])
            self.assertNotIn("Telemetry", case["context"])
        self.assertFalse(list(FIXTURE.glob("*.png")))
        self.assertIn("explicitly authorized", index["publication"])

    def test_projection_cannot_assign_pinned_provenance_to_other_input_bytes(self):
        for name in SOURCE_BLOBS:
            with self.assertRaises(ValueError):
                verify_source_blob(name, b"counterfeit pose bytes")
        with self.assertRaises(ValueError):
            verify_source_blob("../unknown.json", b"counterfeit")

    def test_motion_series_is_distinct_and_visibility_does_not_invent_hop(self):
        cases = {c["id"]: c for c in load("index.json")["cases"]}
        hall, one_leg = cases["factory-hall"], cases["factory-one-leg"]
        self.assertEqual(load(hall["probe"]), load(one_leg["probe"]))
        self.assertNotEqual(load(hall["probe"]), load(cases["factory-held"]["probe"]))
        self.assertEqual(hall["hidden_regions"], [])
        self.assertEqual(one_leg["hidden_regions"], ["left-leg"])
        for group, count, hidden in (("Walk-", 3, []), ("Hop-", 12, ["right-leg"])):
            series = [c for name, c in cases.items() if name.startswith(group)]
            self.assertEqual(len(series), count)
            self.assertEqual(len({c["probe_sha256"] for c in series}), count)
            self.assertEqual(len({c["context"]["CyclePhase"] for c in series}), count)
            self.assertTrue(all(c["hidden_regions"] == hidden for c in series))
        world = cases["World-03-one-leg-hop"]
        self.assertEqual(world["hidden_regions"], ["right-arm", "right-leg"])
        self.assertIn("not explicit hop", world["movement_classification"])

    def test_full_local_replay_pins_inputs_images_and_retains_failed_visual_gate(self):
        folder = FIXTURE.parent / "series-replay"
        report = json.loads((folder / "series.json").read_text("utf-8"))
        cases = {c["id"]: c for c in load("index.json")["cases"]}
        self.assertTrue(report["passed"])
        self.assertEqual(report["case_count"], 19)
        self.assertEqual({c["id"] for c in report["cases"]}, set(cases))
        self.assertEqual(report["consumer_revision"], load("index.json")["source_revision"])
        self.assertFalse(report["visual_qualification"] or report["private_captures_published"])
        self.assertEqual(report["source_sha"], "local-uncommitted")
        self.assertIsNone(report["run_id"])
        self.assertIsNone(report["run_attempt"])
        image_count = 0
        for result in report["cases"]:
            provenance = cases[result["id"]]
            self.assertEqual(result["input_pose_sha256"], provenance["probe_sha256"])
            self.assertEqual(result["asset_sha256"], report["asset_sha256"])
            self.assertEqual(result["hidden_regions"], provenance["hidden_regions"])
            self.assertTrue(result["passed"] and result["source_authority_unchanged"])
            self.assertFalse(result["visual_qualification"] or result["consumer_capture_pixel_equality_claimed"])
            self.assertLess(result["native_vs_decoded_glb_max_error_m"], 1.2e-6)
            self.assertLess(result["decoded_vs_reimport_max_error_m"], 1.2e-6)
            self.assertGreater(result["torso_edges"]["outside_20_percent_count"], 700)
            for name, expected in result["images"].items():
                self.assertEqual(hashlib.sha256((folder / result["id"] / name).read_bytes()).hexdigest(), expected)
                image_count += 1
            if result["id"] in report["rendered_cases"]:
                self.assertTrue(result["images"])
            else:
                self.assertFalse(result["images"])
        self.assertEqual(image_count, 10)


if __name__ == "__main__":
    unittest.main()
