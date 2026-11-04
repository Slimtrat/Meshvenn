"""Actual selected-asset captures stay distinct from old and derived evidence."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.native_pose_capture import CONVENTION, CONTEXT_KEYS, LAYOUT, validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from scripts.extract_stytch_pose_series import capture_profile, encoded, main as extract, verify_source_blob
from scripts import shoulder_consumer_capture as selected
from scripts.shoulder_pose_derivation import inverse
from core.native_pose_capture import multiply

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "example/v2/poses/StytchDollShoulderAligned/complete"


def load(path):
    return json.loads(path.read_text("utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


class ShoulderConsumerCaptureTests(unittest.TestCase):
    def test_profiles_pin_distinct_assets_and_leave_original_defaults(self):
        old, new = capture_profile("original"), capture_profile("shoulder-aligned")
        self.assertEqual(old["asset_sha256"], "76590fd9c335335255f2eb2a4fc0866adf3c5a6a6fad0d4938c9e7550b7dcb57")
        self.assertEqual(old["index_sha256"], digest(old["dataset"] / "index.json"))
        self.assertEqual(new["asset_sha256"], selected.ASSET_SHA)
        self.assertEqual(new["revision"], selected.REVISION)
        self.assertEqual(new["dataset"], FIXTURE)
        self.assertEqual(new["fixture"].name, "StytchDollShoulderAligned")
        self.assertNotEqual(new["revision"], old["revision"])
        self.assertNotEqual(new["index_sha256"], old["index_sha256"])
        with self.assertRaises(ValueError):
            capture_profile("arbitrary-unqualified")

    def test_nineteen_exact_fresh_pairs_validate_all_redundant_matrices(self):
        index = load(FIXTURE / "index.json")
        self.assertEqual(digest(FIXTURE / "index.json"), selected.INDEX_SHA256)
        self.assertEqual(index["source_revision"], selected.REVISION)
        self.assertEqual(index["asset_sha256"], selected.ASSET_SHA)
        self.assertEqual(index["case_count"], 19)
        self.assertEqual(len(index["cases"]), 19)
        expected = {p.removesuffix(".pose.json").replace("/", "-") for p in selected.SOURCE_BLOBS}
        self.assertEqual({c["id"] for c in index["cases"]}, expected)
        rests, poses = None, {}
        for case in index["cases"]:
            for key in ("probe", "matrix_proof"):
                name = case[key]
                self.assertEqual(Path(name).name, name)
                self.assertEqual(digest(FIXTURE / name), case[key+"_sha256"])
                self.assertNotIn(b"\r", (FIXTURE / name).read_bytes())
            probe = NativePoseProbe.from_dict(load(FIXTURE / case["probe"]))
            self.assertEqual(probe.asset_sha256, selected.ASSET_SHA)
            proof = load(FIXTURE / case["matrix_proof"])
            self.assertEqual(validate_matrix_proof(probe, proof), case["matrix_recomposition"])
            actual_rests = {b.name: b.rest for b in probe.bones}
            rests = actual_rests if rests is None else rests
            self.assertEqual(rests, actual_rests)
            relative = case["source_path"].removeprefix(selected.SOURCE_BASE)
            self.assertEqual(case["source_git_blob"], selected.SOURCE_BLOBS[relative])
            self.assertRegex(case["source_json_sha256"], r"^[0-9a-f]{64}$")
            poses[case["id"]] = tuple(b.pose for b in probe.bones)
        self.assertNotEqual(poses["factory-hall"], poses["factory-held"])
        self.assertEqual(len({poses[f"Hop-meshvenn-hop-{i:02}"] for i in range(12)}), 12)
        self.assertEqual(len({poses[f"Walk-meshvenn-walk-{i:02}"] for i in range(3)}), 3)

    def test_public_payload_is_matrix_provenance_only_not_private_pixels_or_controls(self):
        index = load(FIXTURE / "index.json")
        self.assertEqual(len(list(FIXTURE.iterdir())), 39)
        for path in FIXTURE.iterdir():
            self.assertEqual(path.suffix, ".json")
        cases = {c["id"]: c for c in index["cases"]}
        self.assertEqual(cases["factory-one-leg"]["hidden_regions"], ["left-leg"])
        self.assertEqual(cases["Hop-meshvenn-hop-11"]["hidden_regions"], ["right-leg"])
        self.assertEqual(cases["World-03-one-leg-hop"]["hidden_regions"], ["right-arm", "right-leg"])
        self.assertEqual(cases["World-03-one-leg-hop"]["movement_classification"], "walk-approach, not explicit hop")
        for case in index["cases"]:
            self.assertLessEqual(set(case["context"]), CONTEXT_KEYS)
            self.assertRegex(case["capture_sha256"], r"^[0-9a-f]{64}$")
            doc = load(FIXTURE / case["probe"])
            self.assertEqual(set(doc), {"AssetSha256", "CoordinateFrame", "Bones"})
            self.assertEqual(set(load(FIXTURE / case["matrix_proof"])),
                             {"schema_version", "rest_relative", "skeleton_space", "ancestors"})

    def test_blob_pin_refuses_cross_profile_or_mutated_source(self):
        raw = b"private source bytes"
        expected = {"factory-hall.pose.json": git_blob(raw)}
        self.assertEqual(verify_source_blob("factory-hall.pose.json", raw, expected), git_blob(raw))
        with self.assertRaises(ValueError):
            verify_source_blob("factory-hall.pose.json", raw+b" ", expected)
        with self.assertRaises(ValueError):
            verify_source_blob("factory-hall.pose.json", raw, selected.SOURCE_BLOBS)

    def test_pinned_native_raw_reimport_review_has_only_own_fingerprinted_renders(self):
        output = FIXTURE.parent / "replay"
        self.assertEqual(digest(output / "series.json"),
                         "a1ad994cf8156d3f44e74782ade513094310b0fd4ec50fe488240f69cfd2cbdc")
        report, index = load(output / "series.json"), load(FIXTURE / "index.json")
        self.assertTrue(report["passed"] and report["replay_is_actual_consumer_capture"])
        self.assertEqual(report["asset_sha256"], selected.ASSET_SHA)
        self.assertEqual(report["consumer_revision"], selected.REVISION)
        self.assertEqual(report["source_sha"], "5871fbae8be4ae2d735468f466931e47f442da10")
        self.assertEqual(report["dataset_sha256"], selected.INDEX_SHA256)
        self.assertEqual(report["capture_profile"], "shoulder-aligned")
        self.assertFalse(report["visual_qualification"] or report["private_captures_published"])
        expected = {case["id"]: case for case in index["cases"]}
        self.assertEqual(len(report["cases"]), 19)
        seen = set()
        for case in report["cases"]:
            self.assertTrue(case["passed"] and case["source_authority_unchanged"])
            self.assertEqual(case["input_pose_sha256"], expected[case["id"]]["probe_sha256"])
            self.assertEqual(case["hidden_regions"], expected[case["id"]]["hidden_regions"])
            self.assertFalse(case["visual_qualification"] or case["consumer_capture_pixel_equality_claimed"])
            self.assertLess(case["native_rest_error_in_heights"], 2e-6)
            self.assertLess(case["glb_rest_world_max_error"], 2e-6)
            for key in ("native_vs_decoded_glb_max_error_m", "decoded_vs_reimport_max_error_m"):
                self.assertLess(case[key], 2e-5 * 1.82)
            for key, value in load(output / case["id"] / "replay.json").items():
                self.assertEqual(case[key], value)
            for name, sha in case["images"].items():
                self.assertEqual(Path(name).name, name)
                path = output / case["id"] / name
                self.assertEqual(digest(path), sha)
                self.assertNotEqual(sha, expected[case["id"]]["capture_sha256"])
                seen.add(path)
            if case["id"] in report["rendered_cases"]:
                framing = case["review_framing"]
                self.assertTrue(framing["evaluated_visible_geometry_only"])
                self.assertFalse(framing["pose_or_material_edits"])
                visible = {"Doll_"+r.replace("-", "_") for r in
                           {"body-core", "left-arm", "right-arm", "left-leg", "right-leg"}-set(case["hidden_regions"])}
                self.assertEqual(set(framing["visible_meshes"]), visible)
                self.assertTrue({"review_front.png", "review_back.png"} <= case["images"].keys())
            else:
                self.assertIsNone(case["review_framing"])
        self.assertEqual(len(seen), 21)
        self.assertEqual(seen, set(output.rglob("*.png")))

    def test_consumer_ancestor_squash_is_not_mislabeled_as_local_skin_scale(self):
        proof = load(FIXTURE / "Hop-meshvenn-hop-11.matrices.json")
        lengths = [[math.sqrt(sum(a["Local"][c*3+r]**2 for r in range(3)))
                    for c in range(3)] for a in proof["ancestors"]]
        self.assertTrue(any(max(row)-min(row) > .1 for row in lengths))
        for case in ("factory-hall", "factory-held", "Hop-meshvenn-hop-11"):
            probe = NativePoseProbe.from_dict(load(FIXTURE / (case+".json")))
            for bone in probe.bones:
                delta = multiply(inverse(bone.rest), bone.pose)
                for c in range(3):
                    self.assertAlmostEqual(sum(delta[r][c]**2 for r in range(3)), 1, delta=2e-6)

    def test_incomplete_input_fails_before_any_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/"private", Path(folder)/"public"
            source.mkdir()
            with self.assertRaises(ValueError):
                extract(["--profile", "shoulder-aligned", "--input", str(source), "--output", str(output)])
            self.assertFalse(output.exists())

    def test_corrupt_png_proof_or_unqualified_index_fails_atomically(self):
        index = load(FIXTURE / "index.json")
        for mutation in ("png", "proof", "index"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                source, output = Path(folder)/"private", Path(folder)/"public"
                source.mkdir()
                expected = {}
                for case in index["cases"]:
                    doc, proof = load(FIXTURE / case["probe"]), load(FIXTURE / case["matrix_proof"])
                    relative = case["source_path"].removeprefix(selected.SOURCE_BASE)
                    path = source/relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    png = b"PRIVATE PNG BYTES"
                    raw = {**doc, "SchemaVersion": 1, "MatrixLayout": LAYOUT, "PoseConvention": CONVENTION,
                           "CaptureFile": case["capture_filename"], "CaptureSha256": hashlib.sha256(png).hexdigest(),
                           "Context": {"Consumer": "test", "Private": "DO NOT PUBLISH"},
                           "Regions": [{"Id": r, "Visible": r not in case["hidden_regions"]}
                                       for r in ("body-core", "left-arm", "right-arm", "left-leg", "right-leg")],
                           "Ancestors": [{**a, "Name": "PRIVATE"} for a in proof["ancestors"]],
                           "Mounts": ["PRIVATE"], "Controls": ["PRIVATE"],
                           "Bones": [{**b, "RestRelative": proof["rest_relative"][b["Name"]],
                                      "SkeletonSpace": proof["skeleton_space"][b["Name"]]} for b in doc["Bones"]]}
                    if mutation == "proof":
                        raw["Bones"][0]["RestRelative"][9] += .1
                    data = encoded(raw)
                    path.write_bytes(data)
                    path.with_name(case["capture_filename"]).write_bytes(png+b"wrong" if mutation == "png" else png)
                    expected[relative] = git_blob(data)
                profile = {**capture_profile("shoulder-aligned"), "source_blobs": expected}
                with patch("scripts.extract_stytch_pose_series.capture_profile", return_value=profile):
                    with self.assertRaises(ValueError):
                        extract(["--profile", "shoulder-aligned", "--input", str(source), "--output", str(output)])
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
