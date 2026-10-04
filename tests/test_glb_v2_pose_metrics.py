"""Independent checks for the geometric deformation score and CI gates."""
import math
import copy
import unittest

from scripts.glb_v2_pose_metrics import joint_edge_summary, pose_quality_summary, pose_acceptance, check_pose_quality, check_pose_roundtrip


class PoseMetricTests(unittest.TestCase):
    points = ((0,0,0),(.05,0,0),(0,.05,0))
    triangles = ((0,1,2),)

    def score(self, posed, *, rest=None, triangles=None, center=(0,0,0), height=1):
        return joint_edge_summary(self.points if rest is None else rest,posed,
                                  self.triangles if triangles is None else triangles,center,height)

    def test_rigid_rotation_and_translation_do_not_distort_edges(self):
        posed = [(2-y,3+x,4+z) for x,y,z in self.points]
        result = self.score(posed)
        self.assertAlmostEqual(result["max_abs_log_length_ratio"],0,places=12)
        self.assertEqual(result["edge_count"],3)

    def test_uniform_stretch_and_compression_have_equal_log_strain(self):
        for scale in (.2,5):
            result = self.score([tuple(v*scale for v in p) for p in self.points])
            self.assertAlmostEqual(result["p95_abs_log_length_ratio"],math.log(5))
            self.assertEqual(result["collapsed_fraction"],float(scale==.2))
            self.assertEqual(result["stretched_fraction"],float(scale==5))

    def test_seams_and_duplicate_faces_do_not_bias_sample_count(self):
        rest = self.points*2
        result = self.score(rest,rest=rest,triangles=((0,1,2),(3,4,5),(2,1,0)))
        self.assertEqual(result["edge_count"],3)
        # A stretched duplicate cannot be hidden behind the first seam copy.
        posed = (*self.points,*(tuple(v*5 for v in p) for p in self.points))
        self.assertAlmostEqual(self.score(posed,rest=rest,triangles=((0,1,2),(3,4,5)))["p95_abs_log_length_ratio"],math.log(5))

    def test_zero_rest_edges_are_excluded_but_posed_collapse_is_counted(self):
        result = self.score(((0,0,0),)*3,triangles=((0,0,1),(0,1,2)))
        self.assertEqual(result["edge_count"],3)
        self.assertEqual(result["collapsed_fraction"],1)
        self.assertTrue(math.isfinite(result["max_abs_log_length_ratio"]))

    def test_uniform_scale_translation_and_triangle_order_do_not_change_score(self):
        posed = [tuple(v*1.5 for v in p) for p in self.points]
        baseline = self.score(posed)
        move = lambda points: [tuple(v*1000+7 for v in p) for p in points]
        other = self.score(move(posed),rest=move(self.points),height=1000,center=(7,7,7),triangles=((2,1,0),))
        self.assertEqual(baseline,other)

    def test_missing_or_invalid_measurements_cannot_pass(self):
        for posed in ((),((math.nan,0,0),)*3,self.points[:2]):
            with self.assertRaises(ValueError):
                self.score(posed)
        for height in (0,math.inf,-1):
            with self.assertRaises(ValueError):
                self.score(self.points,height=height)
        for triangles in ((),((0,1,8),),((0,1,True),),((0,1),)):
            with self.assertRaises(ValueError):
                self.score(self.points,triangles=triangles)
        with self.assertRaises(ValueError):
            self.score(self.points,center=(0,0,10))

    def test_summary_uses_the_worst_pose_not_a_diluted_average(self):
        poses = [{"id":str(i),"joint_edges":self.score(self.points),
                  "opposite_mean_displacement_in_heights":0,"posed_mean_displacement_in_heights":.1} for i in range(16)]
        poses[3]["joint_edges"] = self.score([tuple(v*5 for v in p) for p in self.points])
        result = pose_quality_summary(poses)
        self.assertAlmostEqual(result["worst_p95_abs_log_length_ratio"],math.log(5))
        with self.assertRaises(AssertionError):
            check_pose_quality(result,pose_acceptance("quaternius_ual1"))
        with self.assertRaises(ValueError):
            pose_quality_summary(poses+poses)

    def test_every_quality_budget_is_enforced_including_static_and_opposite_limbs(self):
        acceptance = pose_acceptance("rigged_figure")
        good = dict(acceptance,pose_count=16)
        check_pose_quality(good,acceptance)
        for name,value in acceptance.items():
            bad = dict(good)
            bad[name] = 0 if name.startswith("min_") else value+.01
            with self.assertRaises(AssertionError,msg=name):
                check_pose_quality(bad,acceptance)
            bad[name] = math.nan
            with self.assertRaises(AssertionError):
                check_pose_quality(bad,acceptance)
        with self.assertRaises(AssertionError):
            check_pose_quality(dict(good,pose_count=15),acceptance)

    def test_roundtrip_checks_each_matching_probe_not_only_overall_limits(self):
        before = {"poses":[{"id":str(i),"joint_edges":self.score(self.points),
                            "posed_mean_displacement_in_heights":.1,
                            "opposite_mean_displacement_in_heights":0} for i in range(16)]}
        check_pose_roundtrip(before,copy.deepcopy(before))
        for mutation in ("displacement","strain","count","missing","renamed","duplicate"):
            after = copy.deepcopy(before)
            if mutation == "displacement":
                after["poses"][0]["posed_mean_displacement_in_heights"] = .12
            elif mutation == "strain":
                after["poses"][0]["joint_edges"]["max_abs_log_length_ratio"] = .03
            elif mutation == "count":
                after["poses"][0]["joint_edges"]["edge_count"] = 4
            elif mutation == "missing":
                after["poses"].pop()
            elif mutation == "renamed":
                after["poses"][0]["id"] = "other"
            else:
                after["poses"][0]["id"] = "1"
            with self.assertRaises(AssertionError,msg=mutation):
                check_pose_roundtrip(before,after)
