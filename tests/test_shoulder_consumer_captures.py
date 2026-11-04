"""Actual selected-asset captures stay distinct from old and derived evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.native_pose_capture import CONVENTION, CONTEXT_KEYS, LAYOUT, validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from scripts.extract_stytch_pose_series import capture_profile, encoded, main as extract, verify_source_blob
from scripts import shoulder_consumer_capture as selected

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
