"""Pure tests for canonical motion source detection and semantic mapping."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "implementations" / "canonical_motion" / "mapping.py"
SPEC = importlib.util.spec_from_file_location("canonical_motion_mapping", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load canonical motion mapping module")
mapping = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mapping
SPEC.loader.exec_module(mapping)


class CanonicalMotionMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_bones = set(mapping.RIGGED_FIGURE_PROFILE.required_bones)
        self.target_semantics = {
            role: role for role in ("root", *mapping.CANONICAL_ANIMATED_ROLES)
        }

    def test_detects_rigged_figure_from_required_bones_and_allows_extras(self) -> None:
        profile = mapping.detect_source_profile(self.source_bones | {"unused_joint"})
        self.assertEqual(profile.identifier, "rigged-figure-v1")

    def test_rejects_incomplete_source_profile(self) -> None:
        self.source_bones.remove("arm_joint_L_2")
        with self.assertRaisesRegex(ValueError, "arm_joint_L_2"):
            mapping.detect_source_profile(self.source_bones)

    def test_resolves_all_seventeen_roles_and_keeps_root_out_of_mapping(self) -> None:
        resolved = mapping.resolve_bone_map(
            self.source_bones,
            self.target_semantics,
            self.target_semantics.values(),
        )
        self.assertEqual(len(resolved.entries), 17)
        self.assertEqual(resolved.animated_roles, mapping.CANONICAL_ANIMATED_ROLES)
        self.assertNotIn("root", resolved.source_bone_map)
        self.assertEqual(resolved.source_bone_map["upper_arm.L"], "arm_joint_L_1")

    def test_requires_fixed_root_and_every_target_role(self) -> None:
        without_root = dict(self.target_semantics)
        del without_root["root"]
        with self.assertRaisesRegex(ValueError, "fixed semantic root"):
            mapping.resolve_bone_map(self.source_bones, without_root, without_root.values())

        without_hand = dict(self.target_semantics)
        del without_hand["hand.R"]
        with self.assertRaisesRegex(ValueError, "hand.R"):
            mapping.resolve_bone_map(
                self.source_bones,
                without_hand,
                self.target_semantics.values(),
            )


if __name__ == "__main__":
    unittest.main()
