"""A constant in-place belt speed is not slide; additional drift is visible."""
import copy
import math
import unittest

from scripts.glb_v2_contact_metrics import (
    SIDES, dense_frames, compare_contacts, check_contact_budgets,
    compare_contact_roundtrip, check_contact_roundtrip, contact_acceptance, LOCOMOTION_CLIPS, validate_observations,
)


def observations(*, speed=.2, z=.01, fps=60, end=12, step=1):
    return {"probes": {side: [[sign * .05, y, 0] for y in (-.05, 0, .05)]
                       for side, sign in (("L", 1), ("R", -1))},
            "sample_step":step,
            "clips": [{"name": "Walk", "frame_start": 0, "frame_end": end, "fps": fps,
                       "samples": [{"frame": frame, "feet": {
                           side: {"centroid": [sign * .05, speed * frame / fps, z], "min_z": z}
                           for side, sign in (("L", 1), ("R", -1))}}
                                   for frame in dense_frames(0, end, step=step)]}]}


def budgets():
    return {"Walk": {"source_windows": {"L": 1, "R": 1}, "penetration": .01, "hover": .03, "drift": .01}}


class ContactMetricsTests(unittest.TestCase):
    def test_half_frame_clock_and_seconds_are_consistent(self):
        self.assertEqual(dense_frames(0,2,step=.5),(0,.5,1,1.5,2))
        source = observations(speed=-.4,step=.5)
        report = compare_contacts(source,source)
        self.assertEqual(report["sole_sample_count"],50)
        self.assertLess(report["clips"][0]["source"]["drift"],1e-12)
        self.assertAlmostEqual(report["clips"][0]["windows"][0]["source_velocity_in_heights_per_second"][1],-.4)
        target = observations(speed=-.8,step=.5)
        self.assertAlmostEqual(compare_contacts(source,target)["clips"][0]["target"]["drift"],.08)
        short = observations(end=4,step=.5)
        self.assertEqual(compare_contacts(short,short)["window_count"],0)

    def test_invalid_or_missing_half_clock_fails(self):
        for step in (True,.25,0,math.nan,math.inf,"0.5"):
            with self.assertRaises(ValueError): dense_frames(0,2,step=step)
        source = observations(step=.5)
        source["clips"][0]["samples"].pop(1)
        with self.assertRaises(ValueError): validate_observations(source)
        with self.assertRaises(AssertionError): check_contact_roundtrip(observations(),observations(step=.5))

    def test_dense_sampling_includes_all_endpoints(self):
        self.assertEqual(dense_frames(1., 4.), (1, 2, 3, 4))
        for bounds in ((1, 1), (3, 1), (0, .5), (True, 3), (math.nan, 4), (0, math.inf)):
            with self.assertRaises(ValueError): dense_frames(*bounds)

    def test_treadmill_travel_is_not_reported_as_drift(self):
        for speed in (0, .2, -2):
            report = check_contact_budgets(observations(speed=speed), observations(speed=speed), budgets())
            self.assertEqual(report["window_count"], 2)
            self.assertLess(report["clips"][0]["target"]["drift"], 1e-12)
            self.assertAlmostEqual(report["clips"][0]["windows"][0]["source_velocity_in_heights_per_second"][1], speed)

    def test_added_constant_slide_cannot_be_fitted_away(self):
        source, target = observations(speed=.2), observations(speed=.4)
        score = compare_contacts(source, target)["clips"][0]
        self.assertAlmostEqual(score["target"]["drift"], .04)
        self.assertLess(score["source"]["drift"], 1e-12)
        with self.assertRaises(AssertionError): check_contact_budgets(source, target, budgets())

    def test_candidate_cannot_hide_its_contacts_by_floating(self):
        source, target = observations(), observations(z=.2)
        score = compare_contacts(source, target)
        self.assertEqual(score["window_count"], 2)
        self.assertEqual(score["clips"][0]["target"]["hover"], .2)
        with self.assertRaises(AssertionError): check_contact_budgets(source, target, budgets())

    def test_one_penetrating_frame_or_foot_fails(self):
        source, target = observations(), observations()
        target["clips"][0]["samples"][6]["feet"]["R"]["min_z"] = -.1
        self.assertEqual(compare_contacts(source, target)["clips"][0]["target"]["penetration"], .1)
        with self.assertRaises(AssertionError): check_contact_budgets(source, target, budgets())

    def test_flight_and_short_ground_intervals_are_not_contacts(self):
        for source in (observations(z=.2), observations(end=4)):
            report = compare_contacts(source, copy.deepcopy(source))
            self.assertEqual(report["window_count"], 0)
            self.assertIsNone(report["clips"][0]["target"]["drift"])
            with self.assertRaises(AssertionError): check_contact_budgets(source, source, budgets())

    def test_contiguous_windows_do_not_join_across_flight(self):
        source = observations(end=20)
        source["clips"][0]["samples"][10]["feet"]["L"]["min_z"] = .1
        source["clips"][0]["samples"][10]["feet"]["L"]["centroid"][2] = .1
        windows = compare_contacts(source, source)["clips"][0]["windows"]
        self.assertEqual([(w["side"], w["frame_start"], w["frame_end"]) for w in windows],
                         [("L", 0, 8), ("L", 12, 20), ("R", 0, 20)])

    def test_near_ground_fast_vertical_swing_is_excluded(self):
        source = observations()
        for sample in source["clips"][0]["samples"]:
            for side in SIDES:
                sample["feet"][side]["centroid"][2] = .05 + sample["frame"] / 60
        self.assertEqual(compare_contacts(source, source)["window_count"], 0)

    def test_duration_threshold_uses_seconds_not_sample_count(self):
        self.assertEqual(compare_contacts(observations(fps=120, end=6), observations(fps=120, end=6))["window_count"], 0)
        self.assertEqual(compare_contacts(observations(fps=24, end=2), observations(fps=24, end=2))["window_count"], 2)

    def test_roundtrip_checks_every_frame_including_flight(self):
        source, target = observations(z=.2), observations(z=.2)
        self.assertEqual(check_contact_roundtrip(source, target)["sole_sample_count"], 26)
        target["clips"][0]["samples"][7]["feet"]["R"]["centroid"][0] += .005
        score = compare_contact_roundtrip(source, target)
        self.assertAlmostEqual(score["max_error_in_heights"], .005)
        self.assertEqual(score["worst_sample"], {"clip": "Walk", "frame": 7, "side": "R"})
        with self.assertRaises(AssertionError): check_contact_roundtrip(source, target)

    def test_roundtrip_checks_minimum_not_just_centroid(self):
        source, target = observations(), observations()
        target["clips"][0]["samples"][1]["feet"]["L"]["min_z"] -= .002
        with self.assertRaises(AssertionError): check_contact_roundtrip(source, target)

    def test_missing_duplicate_samples_feet_clips_or_probes_fail_closed(self):
        source = observations()
        for mutation in ("clip", "duplicate_clip", "sample", "duplicate_sample", "foot", "probe", "probe_position", "fps", "range"):
            target = copy.deepcopy(source)
            clip = target["clips"][0]
            if mutation == "clip": clip["name"] = "unknown"
            elif mutation == "duplicate_clip": target["clips"] *= 2
            elif mutation == "sample": clip["samples"].pop(3)
            elif mutation == "duplicate_sample": clip["samples"][3] = clip["samples"][2]
            elif mutation == "foot": clip["samples"][3]["feet"].pop("R")
            elif mutation == "probe": target["probes"]["L"].pop()
            elif mutation == "probe_position": target["probes"]["L"][0][0] += .01
            elif mutation == "fps": clip["fps"] = 24
            else: clip["frame_start"] = 1
            with self.subTest(mutation=mutation):
                with self.assertRaises((ValueError, AssertionError)): check_contact_roundtrip(source, target)

    def test_nonfinite_and_inconsistent_observations_fail(self):
        for value in (math.nan, math.inf, True, "0"):
            for key in ("min_z", "fps", "probe", "frame", "centroid"):
                source = observations()
                if key == "fps": source["clips"][0]["fps"] = value
                elif key == "probe": source["probes"]["L"][0][0] = value
                elif key == "frame": source["clips"][0]["samples"][0]["frame"] = value
                elif key == "centroid": source["clips"][0]["samples"][0]["feet"]["L"]["centroid"][0] = value
                else: source["clips"][0]["samples"][0]["feet"]["L"][key] = value
                with self.subTest(value=value, key=key):
                    with self.assertRaises(ValueError): check_contact_roundtrip(source, source)
        source = observations()
        source["clips"][0]["samples"][0]["feet"]["L"]["min_z"] = .1
        with self.assertRaises(ValueError): compare_contacts(source, source)

    def test_left_and_right_patches_cannot_share_a_reference_point(self):
        source = observations()
        source["probes"]["R"][0] = source["probes"]["L"][0]
        with self.assertRaises(ValueError): compare_contacts(source, source)

    def test_invalid_limits_or_missing_coverage_cannot_disable_gates(self):
        source = observations()
        for value in (math.nan, math.inf, -1, True):
            with self.assertRaises(ValueError): check_contact_roundtrip(source, source, tolerance=value)
            for metric in ("penetration", "hover", "drift"):
                budget = budgets(); budget["Walk"][metric] = value
                with self.assertRaises(ValueError): check_contact_budgets(source, source, budget)
        with self.assertRaises(ValueError): check_contact_budgets(source, source, {})
        budget = budgets(); budget["Walk"]["source_windows"]["R"] = 2
        with self.assertRaises(AssertionError): check_contact_budgets(source, source, budget)

    def test_unmeasured_clip_is_explicit_not_a_passing_zero(self):
        source = observations(z=.2)
        budget = {"Walk": {"source_windows": {"L": 0, "R": 0}, "penetration": None, "hover": None, "drift": None}}
        report = check_contact_budgets(source, source, budget)
        self.assertEqual(report["gated_clip_names"], [])
        self.assertEqual(report["unmeasured_clip_names"], ["Walk"])
        self.assertEqual(report["clips"][0]["coverage"], "unmeasured")
        budget["Walk"]["hover"] = 0
        with self.assertRaises(ValueError): check_contact_budgets(source, source, budget)

    def test_baselines_pin_all_locomotion_labels_and_both_modes(self):
        for asset, names in LOCOMOTION_CLIPS.items():
            for preserved in (False, True):
                budget = contact_acceptance(asset,preserve_pelvis_height=preserved)
                self.assertEqual(set(budget), set(names))
                for value in budget.values():
                    measured = sum(value["source_windows"].values()) > 0
                    self.assertEqual(value["hover"] is not None, measured)



if __name__ == "__main__":
    unittest.main()
