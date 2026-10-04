"""Combined probes must catch local failures and geometric export drift."""
import copy
from dataclasses import asdict
import math
import unittest

from scripts.glb_v2_combined_metrics import (
    combined_cases, combined_summary, combined_acceptance,
    check_combined_quality, check_combined_roundtrip, validate_sample_reference,
)


def good_report():
    edges = {"edge_count": 12, "p95_abs_log_length_ratio": .1,
             "max_abs_log_length_ratio": .2, "min_length_ratio": .9,
             "max_length_ratio": 1.1, "collapsed_fraction": 0, "stretched_fraction": 0}
    cases = [{"id": spec.identifier,
              "rotations": [asdict(r) for r in spec.rotations],
              "joint_edges": {r.bone: dict(edges) for r in spec.rotations},
              "region_response": {label: .1 if label in spec.active_regions else 0
                                  for label in ("arm.L", "arm.R", "leg.L", "leg.R")},
              "sample_positions_in_heights": [[.1, .2, .3], [.2, .3, .4]]}
             for spec in combined_cases()]
    return {"sample_reference": {"height": 2, "positions": [[0, 0, 0], [1, 0, 2]]},
            "cases": cases, **combined_summary(cases)}


def refresh(report):
    report.update(combined_summary(report["cases"]))
    return report


class CombinedMetricTests(unittest.TestCase):
    def test_exact_bilateral_signed_chain_and_body_coverage(self):
        specs = combined_cases()
        expected = {f"{family}.{side}/{tag}/{sign}"
                    for family, tags in (("arm", ("reach", "cross-plane", "counter-bend", "partial")),
                                         ("leg", ("fold", "abduct", "counter-bend", "partial")),
                                         ("body", ("reach-fold",)))
                    for tag in tags for side in ("L", "R") for sign in ("-1", "+1")}
        self.assertEqual({s.identifier for s in specs}, expected)
        self.assertEqual(len(specs), 36)
        self.assertEqual(sum(len(s.rotations) for s in specs), 80)
        for spec in specs:
            for child, parent in (("forearm", "upper_arm"), ("shin", "thigh")):
                names = [r.bone for r in spec.rotations]
                side = spec.identifier.split("/")[0][-1]
                if f"{child}.{side}" in names:
                    self.assertLess(names.index(f"{parent}.{side}"), names.index(f"{child}.{side}"))
            self.assertEqual(len(spec.active_regions), 2 if spec.identifier.startswith("body") else 1)

    def test_all_fixture_gates_accept_valid_complete_reports(self):
        for asset in ("rigged_figure", "quaternius_human", "quaternius_ual1"):
            check_combined_quality(good_report(), combined_acceptance(asset))

    def test_changed_axis_angle_or_parent_order_cannot_masquerade_as_a_known_case(self):
        for mutation in ("axis", "angle", "order"):
            report = good_report()
            rotations = report["cases"][0]["rotations"]
            if mutation == "axis": rotations[0]["world_axis"] = "X"
            elif mutation == "angle": rotations[0]["degrees"] = 30
            else: rotations.reverse()
            with self.assertRaises(ValueError):
                combined_summary(report["cases"])

    def test_worst_joint_in_one_pose_is_not_diluted(self):
        report = good_report()
        report["cases"][0]["joint_edges"]["forearm.L"]["max_abs_log_length_ratio"] = 2
        refresh(report)
        self.assertEqual(report["worst_abs_log_length_ratio"], 2)
        with self.assertRaises(AssertionError):
            check_combined_quality(report, combined_acceptance("rigged_figure"))

    def test_every_budget_is_enforced_from_individual_measurements(self):
        fields = {"worst_p95_abs_log_length_ratio": "p95_abs_log_length_ratio",
                  "worst_abs_log_length_ratio": "max_abs_log_length_ratio",
                  "worst_collapsed_fraction": "collapsed_fraction",
                  "worst_stretched_fraction": "stretched_fraction"}
        for asset in ("rigged_figure", "quaternius_human", "quaternius_ual1"):
            acceptance = combined_acceptance(asset)
            for field, limit in acceptance.items():
                report = good_report()
                case = report["cases"][0]
                if field in fields:
                    edges = case["joint_edges"]["forearm.L"]
                    edges[fields[field]] = limit + .01
                    edges["max_abs_log_length_ratio"] = max(edges["max_abs_log_length_ratio"], edges["p95_abs_log_length_ratio"])
                else:
                    case["region_response"]["arm.L" if field.startswith("min_") else "leg.L"] = 0 if field.startswith("min_") else limit + .01
                with self.assertRaises(AssertionError, msg=(asset, field)):
                    check_combined_quality(refresh(report), acceptance)

    def test_missing_duplicate_or_renamed_cases_and_joints_fail(self):
        for mutation in ("missing", "duplicate", "renamed", "joint", "region"):
            report = good_report()
            if mutation == "missing":
                report["cases"].pop()
            elif mutation == "duplicate":
                report["cases"][-1] = report["cases"][0]
            elif mutation == "renamed":
                report["cases"][0]["id"] = "unknown"
            elif mutation == "joint":
                report["cases"][0]["joint_edges"].pop("forearm.L")
            else:
                report["cases"][0]["region_response"].pop("leg.R")
            with self.assertRaises(ValueError, msg=mutation):
                combined_summary(report["cases"])

    def test_invalid_edge_fields_cannot_hide_behind_an_earlier_valid_maximum(self):
        for field in good_report()["cases"][0]["joint_edges"]["forearm.L"]:
            for value in (math.nan, math.inf, -1, True):
                report = good_report()
                report["cases"][-1]["joint_edges"]["shin.R"][field] = value
                with self.assertRaises(ValueError, msg=(field, value)):
                    combined_summary(report["cases"])
        for mutation in ("missing", "extra", "fraction", "order", "count"):
            report = good_report()
            edges = report["cases"][0]["joint_edges"]["forearm.L"]
            if mutation == "missing": edges.pop("min_length_ratio")
            elif mutation == "extra": edges["unexpected"] = 0
            elif mutation == "fraction": edges["collapsed_fraction"] = 1.1
            elif mutation == "order": edges["min_length_ratio"] = 1.2
            else: edges["edge_count"] = 0
            with self.assertRaises(ValueError):
                combined_summary(report["cases"])

    def test_invalid_response_and_stale_or_missing_summary_fail(self):
        for value in (math.nan, math.inf, -1, True):
            report = good_report()
            report["cases"][-1]["region_response"]["arm.L"] = value
            with self.assertRaises(ValueError):
                combined_summary(report["cases"])
        for mutation in ("changed", "missing", "nan"):
            report = good_report()
            if mutation == "missing": report.pop("pose_count")
            else: report["worst_abs_log_length_ratio"] = math.nan if mutation == "nan" else 0
            with self.assertRaises(AssertionError):
                check_combined_quality(report, combined_acceptance("rigged_figure"))

    def test_reference_requires_positive_height_and_finite_bounded_samples(self):
        for height in (0, -1, math.nan, math.inf, True):
            with self.assertRaises(ValueError):
                validate_sample_reference({"height": height, "positions": [[0, 0, 0]]})
        for points in ([], [[0, 0]], [[0, 0, math.nan]], [[0, 0, 0]]*81):
            with self.assertRaises(ValueError):
                validate_sample_reference({"height": 1, "positions": points})

    def test_roundtrip_compares_each_sample_even_when_all_metrics_are_identical(self):
        before = good_report()
        after = copy.deepcopy(before)
        self.assertEqual(check_combined_roundtrip(before, after)["max_sample_position_error_in_heights"], 0)
        after["cases"][-1]["sample_positions_in_heights"][-1][0] += .001
        self.assertEqual(combined_summary(before["cases"]), combined_summary(after["cases"]))
        with self.assertRaisesRegex(AssertionError, "sampled deformation"):
            check_combined_roundtrip(before, after)

    def test_roundtrip_checks_each_joint_region_reference_and_sample_count(self):
        before = good_report()
        for mutation in ("edge", "count", "region", "reference", "sample", "nan"):
            after = copy.deepcopy(before)
            case = after["cases"][-1]
            if mutation == "edge": case["joint_edges"]["shin.R"]["min_length_ratio"] = .7
            elif mutation == "count": case["joint_edges"]["shin.R"]["edge_count"] += 1
            elif mutation == "region": case["region_response"]["leg.R"] += .001
            elif mutation == "reference": after["sample_reference"]["positions"][0][0] = .1
            elif mutation == "sample": case["sample_positions_in_heights"].pop()
            else: case["sample_positions_in_heights"][0][0] = math.nan
            with self.assertRaises((AssertionError, ValueError), msg=mutation):
                check_combined_roundtrip(before, refresh(after))

    def test_roundtrip_accepts_only_small_individual_numeric_drift(self):
        before = good_report()
        after = copy.deepcopy(before)
        after["cases"][0]["sample_positions_in_heights"][0][0] += .00001
        after["cases"][0]["joint_edges"]["forearm.L"]["min_length_ratio"] += .001
        result = check_combined_roundtrip(before, refresh(after))
        self.assertAlmostEqual(result["max_sample_position_error_in_heights"], .00001)
        self.assertEqual(result["pose_count"], 36)

    def test_empty_or_nonfinite_budgets_are_not_a_way_to_disable_gates(self):
        for budget in ({}, dict(combined_acceptance("rigged_figure"), worst_abs_log_length_ratio=math.inf)):
            with self.assertRaises(ValueError):
                check_combined_quality(good_report(), budget)


if __name__ == "__main__":
    unittest.main()
