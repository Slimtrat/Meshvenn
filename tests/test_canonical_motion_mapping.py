"""Pure tests for canonical motion source detection and semantic mapping."""

from __future__ import annotations

import importlib.util
import json
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

    def test_catalog_contains_distinct_production_profiles(self) -> None:
        self.assertEqual(
            {profile.identifier for profile in mapping.SOURCE_PROFILES},
            {
                "rigged-figure-v1",
                "khronos-fox-v1",
                "threejs-robot-expressive-v1",
                "mixamo-humanoid-v1",
                "unreal-mannequin-v1",
                "meshvenn-canonical-v1",
            },
        )
        certified = {
            profile.identifier: profile.fixture
            for profile in mapping.SOURCE_PROFILES
            if profile.certification == "e2e"
        }
        self.assertEqual(
            certified,
            {
                "rigged-figure-v1": "RiggedFigure.glb",
                "khronos-fox-v1": "Fox.glb",
                "threejs-robot-expressive-v1": "RobotExpressive.glb",
                "mixamo-humanoid-v1": "QuaterniusHuman.glb",
                "unreal-mannequin-v1": "UAL1_Standard.glb",
            },
        )
        self.assertEqual(mapping.KHRONOS_FOX_PROFILE.rig_archetype, "quadruped")
        self.assertEqual(
            mapping.KHRONOS_FOX_PROFILE.compatible_target_rigs,
            ("source-rig-preservation-v1",),
        )
        self.assertTrue(
            all(
                "source-rig-preservation-v1" in profile.compatible_target_rigs
                for profile in mapping.SOURCE_PROFILES
            )
        )
        self.assertTrue(
            all(
                profile.rig_archetype == "humanoid"
                and "canonical-biped-v1" in profile.compatible_target_rigs
                for profile in mapping.SOURCE_PROFILES
                if profile is not mapping.KHRONOS_FOX_PROFILE
            )
        )

    def test_detects_every_registered_profile(self) -> None:
        for profile in mapping.SOURCE_PROFILES:
            with self.subTest(profile=profile.identifier):
                detected = mapping.detect_source_profile(profile.required_bones)
                self.assertEqual(detected.identifier, profile.identifier)

    def test_certified_profiles_resolve_from_real_fixture_skin_joints(self) -> None:
        from core.glb_route import PRESERVE_SOURCE_ROUTE, decide_glb_character_route
        from tests.test_v2_assets import glb_document

        example = ROOT / "example" / "v2"
        manifest = json.loads((example / "manifest.json").read_text(encoding="utf-8"))
        assets = {Path(asset["file"]).name: asset for asset in manifest["assets"]}
        for profile in mapping.SOURCE_PROFILES:
            if profile.certification != "e2e":
                continue
            with self.subTest(profile=profile.identifier):
                asset = assets[profile.fixture]
                document = glb_document(example / asset["file"])
                joints = {document["nodes"][joint]["name"]
                          for skin in document["skins"] for joint in skin["joints"]}
                resolved = mapping.resolve_source_profile(joints)
                self.assertEqual(resolved.profile, profile)
                self.assertEqual(len(resolved.role_to_bone), 17)
                decision = decide_glb_character_route(
                    source_skin_count=asset["skins"], source_profile=profile.identifier,
                    source_archetype=profile.rig_archetype,
                    source_certification=profile.certification,
                    compatible_targets=profile.compatible_target_rigs,
                    source_animation_count=asset["animations"],
                )
                self.assertEqual(decision.route, PRESERVE_SOURCE_ROUTE)
                self.assertFalse(decision.losses)

    def test_mixamo_namespaces_case_and_separators_are_normalized(self) -> None:
        names = {
            f"mixamorig:{name.replace('ForeArm', 'Fore_Arm').swapcase()}"
            for name in mapping.MIXAMO_HUMANOID_PROFILE.required_bones
        }
        profile = mapping.detect_source_profile(names)
        self.assertEqual(profile.identifier, "mixamo-humanoid-v1")
        resolved = mapping.resolve_bone_map(
            names,
            self.target_semantics,
            self.target_semantics.values(),
        )
        self.assertTrue(
            all(name.startswith("mixamorig:") for name in resolved.source_bone_map.values())
        )

    def test_khronos_fox_maps_left_and_right_limbs_without_swapping(self) -> None:
        resolved = mapping.resolve_bone_map(
            mapping.KHRONOS_FOX_PROFILE.required_bones,
            self.target_semantics,
            self.target_semantics.values(),
        )
        self.assertEqual(resolved.profile_id, "khronos-fox-v1")
        self.assertEqual(resolved.source_bone_map["upper_arm.L"], "b_LeftUpperArm_09")
        self.assertEqual(resolved.source_bone_map["thigh.R"], "b_RightLeg01_019")

    def test_robot_expressive_uses_central_palms_as_hand_roles(self) -> None:
        resolved = mapping.resolve_bone_map(
            mapping.THREEJS_ROBOT_EXPRESSIVE_PROFILE.required_bones,
            self.target_semantics,
            self.target_semantics.values(),
        )
        self.assertEqual(resolved.profile_id, "threejs-robot-expressive-v1")
        self.assertEqual(resolved.source_bone_map["hand.L"], "Palm2.L")
        self.assertEqual(resolved.source_bone_map["hand.R"], "Palm2.R")

    def test_rejects_incomplete_source_profile(self) -> None:
        self.source_bones.remove("arm_joint_L_2")
        with self.assertRaisesRegex(ValueError, "arm_joint_L_2"):
            mapping.detect_source_profile(self.source_bones)

    def test_rejection_reports_the_closest_profile_and_coverage(self) -> None:
        partial = set(mapping.UNREAL_MANNEQUIN_PROFILE.required_bones)
        partial.remove("calf_r")
        with self.assertRaisesRegex(
            ValueError,
            'Closest profile "unreal-mannequin-v1" matches 16/17 roles.*calf_r',
        ):
            mapping.detect_source_profile(partial)

    def test_resolves_all_seventeen_roles_and_keeps_root_out_of_mapping(self) -> None:
        source = mapping.resolve_source_profile(self.source_bones)
        self.assertEqual(source.profile.identifier, "rigged-figure-v1")
        self.assertEqual(tuple(source.role_to_bone), mapping.CANONICAL_ANIMATED_ROLES)
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

    def test_rejects_ambiguous_normalized_source_names(self) -> None:
        names = set(mapping.MESHVENN_CANONICAL_PROFILE.required_bones)
        names.add("upper-arm-L")
        with self.assertRaisesRegex(ValueError, "Unsupported motion source skeleton"):
            mapping.detect_source_profile(names)


if __name__ == "__main__":
    unittest.main()
