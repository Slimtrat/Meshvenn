"""Contact IK cannot trade protected motion or coverage for a passing score."""
import copy
import math
import unittest

from scripts.glb_v2_ik_metrics import (
    check_ik_motion, compare_ik_contacts, check_ik_contact_quality,
    check_ik_interframes, integer_surfaces,
)
from tests.test_glb_v2_contact_metrics import observations, budgets
from tests.test_glb_v2_motion_metrics import good_report, rotation


def contacts(*, z=.002, step=1):
    report = observations(z=z,end=8,step=step)
    report["clips"][0]["name"] = "clip"
    return report


class ContactIKMetricsTests(unittest.TestCase):
    def test_scope_allows_only_active_thigh_and_shin(self):
        before,after,source = good_report(),good_report(),contacts()
        after["clips"][0]["samples"][8]["rotations"]["thigh.L"] = rotation(100)
        report = check_ik_motion(before,after,source)
        self.assertGreater(report["max_active_leg_change_degrees"],50)
        for role in ("pelvis","spine","head","foot.L","foot.R","hand.R"):
            candidate = copy.deepcopy(before)
            candidate["clips"][0]["samples"][8]["rotations"][role] = rotation(100)
            with self.subTest(role=role):
                with self.assertRaises(AssertionError): check_ik_motion(before,candidate,source)

    def test_protected_interframes_have_a_separate_budget(self):
        before,after = good_report(),good_report()
        after["clips"][0]["samples"][1]["rotations"]["foot.R"] = rotation(7)
        check_ik_motion(before,after,contacts())
        after["clips"][0]["samples"][1]["rotations"]["foot.R"] = rotation(9)
        with self.assertRaises(AssertionError): check_ik_motion(before,after,contacts())

    def test_unmeasured_and_opposite_foot_remain_unchanged(self):
        before,after = good_report(),good_report()
        after["clips"][0]["samples"][8]["rotations"]["shin.R"] = rotation(100)
        with self.assertRaises(AssertionError): check_ik_motion(before,after,contacts(z=.2))
        source = contacts()
        for sample in source["clips"][0]["samples"]:
            sample["feet"]["R"].update(centroid=[-.05,0,.2],min_z=.2)
        with self.assertRaises(AssertionError): check_ik_motion(before,after,source)

    def test_root_and_invalid_motion_or_source_cannot_pass(self):
        before = good_report()
        after = copy.deepcopy(before)
        after["clips"][0]["samples"][0]["root_offset_in_heights"][0] = .001
        with self.assertRaises(AssertionError): check_ik_motion(before,after,contacts())
        for mutation in ("clip","sample","clock","step","nonfinite"):
            source = contacts()
            clip = source["clips"][0]
            if mutation == "clip": clip["name"] = "missing"
            elif mutation == "sample": clip["samples"].pop()
            elif mutation == "clock": clip["fps"] = 24
            elif mutation == "step": source = contacts(step=.5)
            else: clip["samples"][1]["feet"]["L"]["min_z"] = math.nan
            with self.subTest(mutation=mutation):
                with self.assertRaises((ValueError,AssertionError)): check_ik_motion(before,before,source)

    def test_relative_path_is_anchored_to_baseline_not_candidate(self):
        source,baseline,target = observations(z=.002),observations(z=.002),observations(z=.002)
        for sample in target["clips"][0]["samples"]:
            sample["feet"]["L"]["centroid"][0] += .02
        report = compare_ik_contacts(source,baseline,target)["clips"][0]
        self.assertAlmostEqual(report["relative_path_errors_in_heights"]["target"],.02)
        with self.assertRaises(AssertionError): check_ik_contact_quality(source,baseline,target,budgets=budgets())

    def test_quality_keeps_source_curvature_but_rejects_added_slide(self):
        source = observations(z=.002)
        for sample in source["clips"][0]["samples"]:
            for foot in sample["feet"].values(): foot["centroid"][1] += .05*math.sin(sample["frame"])
        report = check_ik_contact_quality(source,source,source,budgets=budgets())
        self.assertEqual(report["gated_clip_names"],["Walk"])
        self.assertGreater(report["clips"][0]["source"]["drift"],.01)
        target = copy.deepcopy(source)
        target["clips"][0]["samples"][8]["feet"]["L"]["centroid"][0] += .006
        with self.assertRaises(AssertionError): check_ik_contact_quality(source,source,target,budgets=budgets())

    def test_quality_checks_floor_hover_and_coverage(self):
        source = observations(z=.002)
        for value in (-.001,.02):
            with self.assertRaises(AssertionError):
                check_ik_contact_quality(source,source,observations(z=value),budgets=budgets())
        changed = budgets(); changed["Walk"]["source_windows"]["R"] = 0
        with self.assertRaises(AssertionError): check_ik_contact_quality(source,source,source,budgets=changed)

    def test_unmeasured_is_not_a_passing_zero(self):
        source = observations(z=.2)
        limits = {"Walk":{"source_windows":{"L":0,"R":0}}}
        report = check_ik_contact_quality(source,source,source,budgets=limits)
        self.assertEqual(report["gated_clip_names"],[])
        self.assertIsNone(report["clips"][0]["relative_path_errors_in_heights"]["target"])
        self.assertEqual(report["unmeasured_clip_names"],["Walk"])
        half = observations(z=.2,step=.5)
        self.assertIsNone(check_ik_interframes(source,half,budgets=limits)["max_penetration_in_heights"])

    def test_invalid_source_counts_cannot_weaken_acceptance(self):
        source = observations(z=.002)
        for value in (True,-1,1.0,math.nan):
            limit = budgets(); limit["Walk"]["source_windows"]["L"] = value
            with self.assertRaises(ValueError): check_ik_contact_quality(source,source,source,budgets=limit)

    def test_integer_subset_and_half_floor_gate(self):
        source,half = observations(z=.002),observations(z=.002,step=.5)
        self.assertEqual(integer_surfaces(half),source)
        report = check_ik_interframes(source,half,budgets=budgets())
        self.assertEqual(report["contact_sole_sample_count"],24)
        self.assertEqual(report["max_penetration_in_heights"],0)
        for low in (-.002,.02):
            candidate = copy.deepcopy(half)
            candidate["clips"][0]["samples"][7]["feet"]["R"].update(min_z=low,centroid=[-.05,0,max(low,.002)])
            with self.assertRaises(AssertionError): check_ik_interframes(source,candidate,budgets=budgets())

    def test_half_checks_do_not_infer_candidate_windows(self):
        source,half = observations(z=.002),observations(z=.2,step=.5)
        with self.assertRaises(AssertionError): check_ik_interframes(source,half,budgets=budgets())
        for mutation in ("frame","fps","probes","step"):
            candidate = observations(z=.002,step=.5)
            if mutation == "frame": candidate["clips"][0]["samples"].pop(1)
            elif mutation == "fps": candidate["clips"][0]["fps"] = 30
            elif mutation == "probes": candidate["probes"]["L"][0][1] += .01
            else: candidate = observations(z=.002)
            with self.assertRaises((ValueError,AssertionError)): check_ik_interframes(source,candidate,budgets=budgets())
        with self.assertRaises(AssertionError): check_ik_interframes(half,half,budgets=budgets())


if __name__ == "__main__": unittest.main()
