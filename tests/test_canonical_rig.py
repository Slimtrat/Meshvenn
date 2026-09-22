from __future__ import annotations

import math
import unittest

from core.canonical_rig import (
    BoneSpec,
    MeshBounds,
    bounds_from_vertices,
    fallback_weights,
    fit_canonical_biped,
)
from core.rig_contracts import RigOutput
from tests.geometry_contracts_test_support import geometry_output


class CanonicalRigTests(unittest.TestCase):
    def test_bounds_reject_empty_nonfinite_and_flat_meshes(self) -> None:
        with self.assertRaises(ValueError):
            bounds_from_vertices(())
        with self.assertRaises(ValueError):
            bounds_from_vertices(((0, 0, 0), (1, math.nan, 1)))
        with self.assertRaises(ValueError):
            MeshBounds((0, 0, 0), (1, 0, 2))

    def test_fit_has_stable_hierarchy_and_side_convention(self) -> None:
        bounds = MeshBounds((-1, -.2, 0), (1, .2, 2))
        bones = fit_canonical_biped(bounds)
        self.assertEqual(len(bones), 18)
        by_name = {bone.name: bone for bone in bones}
        self.assertEqual(len(by_name), len(bones))
        self.assertEqual(by_name["root"].parent, None)
        self.assertFalse(by_name["root"].deform)
        self.assertEqual(by_name["forearm.L"].parent, "upper_arm.L")
        self.assertEqual(by_name["foot.R"].parent, "shin.R")
        self.assertGreater(by_name["upper_arm.L"].head[0], 0)
        self.assertLess(by_name["upper_arm.R"].head[0], 0)
        self.assertTrue(all(bone.parent is None or bone.parent in by_name for bone in bones))

    def test_fallback_weights_are_bounded_and_normalized(self) -> None:
        bones = fit_canonical_biped(MeshBounds((-1, -.2, 0), (1, .2, 2)))
        for point in ((0, 0, 1), (.7, 0, 1.3), (-.1, -.1, .02)):
            weights = fallback_weights(point, bones)
            self.assertLessEqual(len(weights), 4)
            self.assertAlmostEqual(sum(weights.values()), 1)
            self.assertTrue(all(math.isfinite(weight) and weight > 0 for weight in weights.values()))
        with self.assertRaises(ValueError):
            fallback_weights((0, 0, 0), bones, max_influences=0)
        with self.assertRaises(ValueError):
            fallback_weights((0, 0, 0), (BoneSpec("root", None, (0, 0, 0), (0, 0, 1), False),))

    def test_output_preserves_geometry_and_semantics(self) -> None:
        geometry = geometry_output()
        armature = object()
        output = RigOutput(
            geometry=geometry,
            blender_object=geometry.blender_object,
            armature_object=armature,
            implementation_id="canonical-biped-v1",
            semantic_bones={"pelvis": "pelvis"},
            binding_method="canonical-distance",
        )
        self.assertIs(output.armature_object, armature)
        self.assertEqual(output.semantic_bones["pelvis"], "pelvis")
        with self.assertRaises(ValueError):
            RigOutput(
                geometry=geometry,
                blender_object=object(),
                armature_object=armature,
                implementation_id="canonical-biped-v1",
                semantic_bones={"pelvis": "pelvis"},
                binding_method="canonical-distance",
            )


if __name__ == "__main__":
    unittest.main()
