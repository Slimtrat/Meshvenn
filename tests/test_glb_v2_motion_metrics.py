"""Motion fidelity must reject lost roles, clips, instants and root drift."""
import copy
import json
import math
from pathlib import Path
import unittest

from scripts.glb_v2_motion_metrics import ROLES, FIXTURES, sample_frames, angular_error, compare_motion, check_motion
from scripts.glb_v2_motion_metrics import compare_pelvis_height, check_pelvis_height


def rotation(degrees):
    angle = math.radians(degrees)/2
    return [math.cos(angle),0,0,math.sin(angle)]


def good_report(*, static=False):
    samples = [{"frame":frame, "rotations":{role:rotation(0 if static else frame*10) for role in ROLES},
                "root_offset_in_heights":[0,0,0], "pelvis_height_offset_in_heights":frame/100}
               for frame in sample_frames(0,8)]
    return {"clips":[{"name":"clip", "frame_start":0, "frame_end":8, "fps":60, "samples":samples}]}


class MotionMetricsTests(unittest.TestCase):
    def test_pelvis_height_is_scaled_or_deliberately_discarded(self):
        source = good_report()
        check_pelvis_height(source,source,preserved=True)
        fixed = copy.deepcopy(source)
        for sample in fixed["clips"][0]["samples"]: sample["pelvis_height_offset_in_heights"] = 0
        check_pelvis_height(source,fixed,preserved=False)
        with self.assertRaises(AssertionError): check_pelvis_height(source,fixed,preserved=True)
        with self.assertRaises(AssertionError): check_pelvis_height(source,source,preserved=False)

    def test_pelvis_height_one_bad_sample_and_nonfinite_values_fail(self):
        source = good_report()
        for value in (math.nan, math.inf, True, .1):
            candidate = copy.deepcopy(source)
            candidate["clips"][0]["samples"][1]["pelvis_height_offset_in_heights"] = value
            with self.assertRaises((ValueError,AssertionError)): check_pelvis_height(source,candidate,preserved=True)
        candidate = copy.deepcopy(source)
        candidate["clips"][0]["samples"][1]["pelvis_height_offset_in_heights"] += .001
        report = compare_pelvis_height(source,candidate,preserved=True)
        self.assertAlmostEqual(report["interframe"]["max_error_in_heights"], .001)
        self.assertEqual(report["interframe"]["worst_sample"], {"clip":"clip", "frame":.5})

    def test_pelvis_height_limits_cannot_be_nonfinite_or_negative(self):
        source = good_report()
        for value in (math.nan, math.inf, -1, True):
            for argument in ("integer_limit", "interframe_limit"):
                with self.assertRaises(ValueError): check_pelvis_height(source,source,preserved=True,**{argument:value})

    def test_quaternion_sign_scale_and_known_angle(self):
        self.assertAlmostEqual(angular_error(rotation(30),[-v*2 for v in rotation(30)]),0,places=5)
        self.assertAlmostEqual(angular_error(rotation(10),rotation(80)),70)
        for value in ([0]*4,[1,0,0],[math.nan,0,0,1],[math.inf,0,0,1]):
            with self.assertRaises(ValueError): angular_error(value,rotation(0))

    def test_sampling_includes_endpoints_and_half_frames_without_duplicates(self):
        self.assertEqual(sample_frames(0,1),(0,.5,1))
        self.assertEqual(sample_frames(0.,1.),sample_frames(0,1))
        self.assertEqual(len(sample_frames(0,80)),17)
        self.assertEqual(sample_frames(0,80)[-1],80)
        for bounds in ((0,0),(1,0),(.2,4),(math.nan,4),(True,4)):
            with self.assertRaises(ValueError): sample_frames(*bounds)

    def test_complete_moving_and_static_clips_pass(self):
        for static in (False,True):
            report = good_report(static=static)
            scored = check_motion(report,copy.deepcopy(report),static_clips=("clip",) if static else ())
            self.assertEqual(scored["role_sample_count"],17*17)
            self.assertAlmostEqual(scored["max_integer_rotation_error_degrees"],0,places=5)

    def test_worst_single_role_error_is_not_hidden_by_a_mean(self):
        before = good_report()
        after = copy.deepcopy(before)
        after["clips"][0]["samples"][8]["rotations"]["hand.R"] = rotation(90)
        score = compare_motion(before,after)
        self.assertGreater(score["max_integer_rotation_error_degrees"],40)
        self.assertEqual(score["clips"][0]["worst_integer_sample"],{"frame":4,"role":"hand.R"})
        with self.assertRaises(AssertionError): check_motion(before,after)

    def test_interframe_error_is_gated_separately(self):
        before = good_report()
        after = copy.deepcopy(before)
        after["clips"][0]["samples"][1]["rotations"]["foot.R"] = rotation(10)
        self.assertAlmostEqual(compare_motion(before,after)["max_interframe_rotation_error_degrees"],5)
        with self.assertRaises(AssertionError): check_motion(before,after)

    def test_empty_duplicate_missing_or_extra_clip_cannot_pass(self):
        before = good_report()
        for mutation in ("empty","duplicate","rename","extra"):
            after = copy.deepcopy(before)
            if mutation == "empty": after["clips"] = []
            elif mutation == "duplicate": after["clips"] *= 2
            elif mutation == "rename": after["clips"][0]["name"] = "other"
            else:
                second = copy.deepcopy(after["clips"][0]); second["name"] = "extra"; after["clips"].append(second)
            with self.assertRaises((ValueError,AssertionError)): check_motion(before,after)

    def test_missing_sample_role_invalid_data_or_timing_fail(self):
        before = good_report()
        for mutation in ("sample","role","nan","root","fps","time"):
            after = copy.deepcopy(before)
            clip = after["clips"][0]
            if mutation == "sample": clip["samples"].pop()
            elif mutation == "role": clip["samples"][0]["rotations"].pop("head")
            elif mutation == "nan": clip["samples"][0]["rotations"]["head"][0] = math.nan
            elif mutation == "root": clip["samples"][0]["root_offset_in_heights"] = [0,0,math.nan]
            elif mutation == "fps": clip["fps"] = 24
            else: clip["samples"][1]["frame"] = .7
            with self.assertRaises((ValueError,AssertionError)): check_motion(before,after)

    def test_root_drift_and_constant_moving_clip_fail(self):
        before = good_report()
        after = copy.deepcopy(before)
        after["clips"][0]["samples"][-1]["root_offset_in_heights"][0] = .001
        with self.assertRaises(AssertionError): check_motion(before,after)
        for sample in after["clips"][0]["samples"]:
            sample["root_offset_in_heights"] = [.001,0,0]
        with self.assertRaises(AssertionError): check_motion(before,after)
        flat = good_report(static=True)
        with self.assertRaises(AssertionError): check_motion(flat,flat)
        with self.assertRaises(AssertionError): check_motion(before,before,static_clips=("clip",))
        with self.assertRaises(AssertionError): check_motion(before,before,static_clips=("unknown",))

    def test_nonfinite_or_negative_budget_cannot_disable_the_gate(self):
        for limit in (math.nan,math.inf,-1):
            with self.assertRaises(ValueError): check_motion(good_report(),good_report(),interframe_limit=limit)

    def test_fixture_counts_and_static_labels_match_the_pinned_manifest(self):
        manifest = json.loads((Path(__file__).resolve().parents[1]/"example/v2/manifest.json").read_text())
        assets = {asset["id"]:asset for asset in manifest["assets"]}
        self.assertEqual(sum(spec[2] for spec in FIXTURES.values()),51)
        for identifier,(file,profile,count,static) in FIXTURES.items():
            asset = assets[identifier]
            self.assertEqual(Path(asset["file"]).name,file)
            self.assertEqual(asset["animations"],count)
            self.assertEqual(tuple(asset.get("static_clips",())),static)
            if "profile" in asset: self.assertEqual(asset["profile"],profile)


if __name__ == "__main__":
    unittest.main()
