"""Captured pose parsing must preserve basis columns and reject wrong ABI."""
import hashlib
import json
import math
from pathlib import Path
import unittest

from core.native_pose_probe import FRAME, PARENTS, NativePoseProbe, matrix_rows


def synthetic_probe():
    names = list(PARENTS)
    identity = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    return {"AssetSha256": "a"*64, "CoordinateFrame": FRAME,
            "Bones": [{"Name": n, "Parent": names.index(PARENTS[n]) if PARENTS[n] else -1,
                       "Rest": list(identity), "Pose": list(identity)} for n in names]}


class NativeProbeTests(unittest.TestCase):
    def test_basis_columns_origin_and_parent_first_order(self):
        rows = matrix_rows([0, 1, 0, -1, 0, 0, 0, 0, 1, 4, 5, 6])
        self.assertEqual(rows, ((0, -1, 0, 4), (1, 0, 0, 5), (0, 0, 1, 6), (0, 0, 0, 1)))
        value = synthetic_probe()
        probe = NativePoseProbe.from_dict(value)
        processed = set()
        for bone in probe.ordered():
            self.assertTrue(bone.parent is None or bone.parent in processed)
            processed.add(bone.name)
        names = [b["Name"] for b in value["Bones"]]
        value["Bones"].reverse()
        reversed_names = [b["Name"] for b in value["Bones"]]
        for bone in value["Bones"]:
            if bone["Parent"] >= 0:
                bone["Parent"] = reversed_names.index(names[bone["Parent"]])
        self.assertEqual(probe.ordered(), NativePoseProbe.from_dict(value).ordered())

    def test_wrong_frame_fingerprint_names_and_hierarchy_fail_closed(self):
        bad_values = []
        for key, value in (("CoordinateFrame", "world"), ("AssetSha256", "abc"), ("Bones", [])):
            bad = synthetic_probe()
            bad[key] = value
            bad_values.append(bad)
        for key, value in (("Parent", True), ("Parent", 19), ("Parent", 0), ("Name", "unknown")):
            bad = synthetic_probe()
            bad["Bones"][0][key] = value
            bad_values.append(bad)
        bad = synthetic_probe()
        bad["Bones"][1]["Name"] = "root"
        bad_values.append(bad)
        bad = synthetic_probe()
        bad["Unexpected"] = "ignore me"
        bad_values.append(bad)
        for value in bad_values:
            with self.assertRaises(ValueError):
                NativePoseProbe.from_dict(value)

    def test_nonfinite_boolean_singular_and_mirrored_transforms_rejected(self):
        for key, value in ((0, math.nan), (0, True), (0, 0), (0, -1), (11, math.inf)):
            bad = synthetic_probe()
            bad["Bones"][0]["Pose"][key] = value
            with self.assertRaises(ValueError):
                NativePoseProbe.from_dict(bad)
        with self.assertRaises(ValueError):
            matrix_rows([1]*16)

    def test_hash_case_normalizes_but_rest_and_pose_are_distinct(self):
        value = synthetic_probe()
        value["AssetSha256"] = value["AssetSha256"].upper()
        value["Bones"][0]["Pose"][9] = .25
        probe = NativePoseProbe.from_dict(value)
        self.assertEqual(probe.asset_sha256, "a"*64)
        self.assertEqual(probe.bones[0].rest[0][3], 0)
        self.assertEqual(probe.bones[0].pose[0][3], .25)

    def test_authorized_consumer_fixture_pins_exact_bytes_and_baseline(self):
        folder = Path(__file__).resolve().parents[1] / "example/v2/poses/StytchDoll"
        provenance = json.loads((folder / "provenance.json").read_text("utf-8"))
        captured = (folder / "factory-hall-pose.json").read_bytes()
        expected = "032ad2517bd319a8c87a28a1f978c1bcc0bdac4ca23dce2dc37718d957632d52"
        self.assertEqual(hashlib.sha256(captured).hexdigest(), expected)
        self.assertEqual(provenance["files"], {"factory-hall-pose.json": expected})
        probe = NativePoseProbe.from_dict(json.loads(captured))
        self.assertEqual(probe.asset_sha256, provenance["asset_sha256"])
        baseline = folder.parents[1] / "modular/StytchDoll/character.glb"
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), probe.asset_sha256)
        self.assertEqual(provenance["source_repository"], "Stytch0/Stytch")
        self.assertEqual(provenance["source_revision"], "a0bbe82facb35b7108b10cdcf3b827c82a5c4c72")
        self.assertEqual(provenance["duplicate_snapshot"]["sha256"], expected)
        self.assertEqual(provenance["missing_pose_matrices_at_revision"], ["held", "walk", "one-leg-hop"])
        self.assertIn("explicitly authorized", provenance["publication"])
        self.assertNotIn("?token=", json.dumps(provenance))
        self.assertNotIn("CC0", provenance["publication"])

    def test_native_replay_proves_fidelity_not_visual_acceptance(self):
        folder = Path(__file__).resolve().parents[1] / "example/v2/poses/StytchDoll"
        provenance = json.loads((folder / "provenance.json").read_text("utf-8"))
        report = json.loads((folder / "replay/replay.json").read_text("utf-8"))
        self.assertEqual(report["asset_sha256"], provenance["asset_sha256"])
        self.assertEqual(report["input_pose_sha256"], provenance["files"]["factory-hall-pose.json"])
        self.assertTrue(report["passed"] and report["source_authority_unchanged"])
        self.assertFalse(report["visual_qualification"])
        self.assertFalse(report["consumer_capture_pixel_equality_claimed"])
        self.assertIsNone(report["run_id"])
        self.assertEqual(report["hidden_region"], "left-leg")
        self.assertLess(report["native_vs_decoded_glb_max_error_m"], 1e-6)
        self.assertLess(report["decoded_vs_reimport_max_error_m"], 1e-6)
        self.assertGreater(report["torso_edges"]["outside_20_percent_count"], 700)
        self.assertEqual(set(report["images"]), {"native_rest.png", "native_pose.png",
                                              "glb_pose.png", "glb_pose_hidden_left-leg.png"})
        for name, expected in report["images"].items():
            self.assertEqual(hashlib.sha256((folder / "replay" / name).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
