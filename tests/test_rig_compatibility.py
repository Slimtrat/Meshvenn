from __future__ import annotations

import unittest

from core.rig_compatibility import (
    RigStructureEvidence,
    assess_rig_compatibility,
    require_target_compatibility,
)


def _structure(*, bones: int = 24) -> RigStructureEvidence:
    return RigStructureEvidence(
        armature_count=1,
        bone_count=bones,
        root_bone_count=1,
        max_hierarchy_depth=6,
        skinned_mesh_count=1,
        rest_dimensions=(1.0, 0.5, 2.0),
    )


class RigCompatibilityTests(unittest.TestCase):
    def test_routes_supported_humanoid_to_canonical_biped(self) -> None:
        report = assess_rig_compatibility(
            _structure(),
            source_profile="rigged-figure-v1",
            declared_archetype="humanoid",
            compatible_targets=("canonical-biped-v1",),
        )
        self.assertEqual(report.source_archetype, "humanoid")
        self.assertTrue(report.routable)
        self.assertEqual(report.semantic_score, 1.0)
        self.assertEqual(report.classification_confidence, 1.0)
        self.assertEqual(report.structure.structural_score, 1.0)

    def test_rejects_recognized_quadruped_for_canonical_biped(self) -> None:
        report = assess_rig_compatibility(
            _structure(),
            source_profile="khronos-fox-v1",
            declared_archetype="quadruped",
            compatible_targets=(),
        )
        self.assertEqual(report.source_archetype, "quadruped")
        self.assertFalse(report.routable)
        self.assertEqual(report.semantic_score, 0.0)
        with self.assertRaisesRegex(ValueError, "quadruped"):
            require_target_compatibility(
                "khronos-fox-v1", "quadruped", (), "canonical-biped-v1"
            )

    def test_routes_quadruped_to_source_preservation(self) -> None:
        report = assess_rig_compatibility(
            _structure(),
            source_profile="khronos-fox-v1",
            declared_archetype="quadruped",
            compatible_targets=("source-rig-preservation-v1",),
            target_rig="source-rig-preservation-v1",
        )
        self.assertTrue(report.routable)
        self.assertEqual(report.semantic_score, 1.0)

    def test_classifies_unregistered_small_rig_as_insufficient(self) -> None:
        report = assess_rig_compatibility(
            _structure(bones=2),
            source_profile=None,
            declared_archetype=None,
        )
        self.assertEqual(report.source_archetype, "insufficient")
        self.assertFalse(report.routable)
        self.assertLess(report.classification_confidence, 0.1)
        self.assertGreater(report.structure.structural_score, 0.0)

    def test_unrigged_geometry_remains_available_for_rig_generation(self) -> None:
        report = assess_rig_compatibility(
            RigStructureEvidence(0, 0, 0, 0, 0, (0.0, 0.0, 0.0)),
            source_profile=None,
            declared_archetype=None,
        )
        self.assertIsNone(report.target_compatible)
        self.assertIsNone(report.semantic_score)
        self.assertFalse(report.routable)


if __name__ == "__main__":
    unittest.main()
