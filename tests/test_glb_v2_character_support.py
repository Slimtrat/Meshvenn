"""Pure tests for end-to-end character benchmark support."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.glb_v2_character_support import assert_unrigged_mesh, normalized_landmarks, connectivity_summary
from scripts.glb_v2_character_support import assert_refinement_quality


class GLBV2CharacterSupportTests(unittest.TestCase):
    def test_refinement_gates_require_real_finite_improvements(self):
        report = {'algorithm':'contour-taubin-v2','topology_preserved':True,'face_orientation_preserved':True,
                  'roughness_before_in_voxels':.1,'roughness_after_in_voxels':.06,
                  'mean_contour_residual_before_in_voxels':.3,'mean_contour_residual_after_in_voxels':.1,
                  'contour_residual_sample_count':100,'contour_residual_valid_samples_before':100,
                  'contour_residual_valid_samples_after':100}
        options = dict(min_roughness_reduction=.2,min_contour_reduction=.5)
        assert_refinement_quality(report,**options)
        for changes in ({'algorithm':'bounded-taubin-v1'}, {'topology_preserved':False},
                        {'roughness_after_in_voxels':.09}, {'mean_contour_residual_after_in_voxels':.2},
                        {'mean_contour_residual_after_in_voxels':None}, {'roughness_before_in_voxels':0},
                        {'roughness_after_in_voxels':float('nan')}, {'roughness_after_in_voxels':-1},
                        {'contour_residual_valid_samples_after':94}, {'roughness_after_in_voxels':True}):
            with self.subTest(changes=changes), self.assertRaises(AssertionError):
                assert_refinement_quality(report|changes,**options)
        assert_refinement_quality({})
        with self.assertRaises(ValueError):
            assert_refinement_quality({},min_contour_reduction=float('nan'))

    def test_connectivity_welds_seams_but_rejects_floating_hands(self):
        points = [(0,0,0),(1,0,0),(0,1,0),(1,0,0),(2,0,0),(0,1,0)]
        self.assertEqual(connectivity_summary(points,[(0,1,2),(3,4,5)])["component_count"],1)
        self.assertEqual(connectivity_summary(points+[(7,0,0)],[(0,1,2),(3,4,5)])["component_count"],2)

    def test_normalization_uses_body_height_and_floor(self) -> None:
        vertices = [(-1, -2, 4), (3, 2, 8)]
        result = normalized_landmarks({"joint": (1, 0, 6)}, vertices)
        self.assertEqual(result["joint"], (0.0, 0.0, 0.5))

    def test_normalization_is_translation_and_scale_invariant(self) -> None:
        first = normalized_landmarks({"joint": (1, 0, 6)}, [(-1, -2, 4), (3, 2, 8)])
        second = normalized_landmarks({"joint": (12, 10, 22)}, [(8, 6, 18), (16, 14, 26)])
        self.assertEqual(first, second)

    def test_degenerate_frame_fails(self) -> None:
        with self.assertRaises(ValueError):
            normalized_landmarks({}, [(0, 0, 1), (2, 2, 1)])

    def test_source_rig_leakage_fails(self) -> None:
        clean = SimpleNamespace(parent=None, modifiers=[], vertex_groups=[])
        assert_unrigged_mesh(clean)
        with self.assertRaises(AssertionError):
            assert_unrigged_mesh(SimpleNamespace(parent=object(), modifiers=[], vertex_groups=[]))
        with self.assertRaises(AssertionError):
            assert_unrigged_mesh(SimpleNamespace(
                parent=None, modifiers=[SimpleNamespace(type="ARMATURE")], vertex_groups=[]
            ))
        with self.assertRaises(AssertionError):
            assert_unrigged_mesh(SimpleNamespace(parent=None, modifiers=[], vertex_groups=[object()]))


if __name__ == "__main__":
    unittest.main()
