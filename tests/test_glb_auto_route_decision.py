from __future__ import annotations

import unittest

from core.glb_route import (
    GEOMETRY_ONLY_ROUTE,
    PRESERVE_SOURCE_ROUTE,
    decide_glb_character_route,
)


class GLBAutoRouteDecisionTests(unittest.TestCase):
    def test_supported_humanoid_is_preserved_without_opt_in_conversion(self) -> None:
        decision = decide_glb_character_route(
            source_skin_count=1,
            source_profile="rigged-figure-v1",
            source_archetype="humanoid",
            source_certification="e2e",
            compatible_targets=(
                "canonical-biped-v1",
                "source-rig-preservation-v1",
            ),
        )
        self.assertEqual(decision.route, PRESERVE_SOURCE_ROUTE)
        self.assertIn("opt-in", decision.reason)
        self.assertFalse(decision.losses)

    def test_non_biped_certified_rig_is_preserved(self) -> None:
        decision = decide_glb_character_route(
            source_skin_count=1,
            source_profile="khronos-fox-v1",
            source_archetype="quadruped",
            source_certification="e2e",
            compatible_targets=("source-rig-preservation-v1",),
        )
        self.assertEqual(decision.route, PRESERVE_SOURCE_ROUTE)
        self.assertIn("preservation adapter", decision.reason)

    def test_static_glb_is_geometry_only(self) -> None:
        decision = decide_glb_character_route(
            source_skin_count=0,
            source_profile=None,
        )
        self.assertEqual(decision.route, GEOMETRY_ONLY_ROUTE)
        self.assertIn("no skin", decision.reason)

    def test_unknown_skinned_rig_is_not_guessed(self) -> None:
        decision = decide_glb_character_route(
            source_skin_count=1,
            source_profile=None,
        )
        self.assertEqual(decision.route, GEOMETRY_ONLY_ROUTE)
        self.assertIn("degraded", decision.reason)
        self.assertIn("source rig and skin", decision.losses)

    def test_contract_only_profile_does_not_claim_automatic_certification(self) -> None:
        decision = decide_glb_character_route(
            source_skin_count=1, source_profile="mixamo-humanoid-v1",
            source_archetype="humanoid", source_certification="contract",
            compatible_targets=("source-rig-preservation-v1", "canonical-biped-v1"),
        )
        self.assertEqual(decision.route, GEOMETRY_ONLY_ROUTE)

    def test_canonical_only_profile_is_not_silently_converted(self) -> None:
        decision = decide_glb_character_route(
            source_skin_count=1, source_profile="test", source_archetype="humanoid",
            source_certification="e2e", compatible_targets=("canonical-biped-v1",),
        )
        self.assertEqual(decision.route, GEOMETRY_ONLY_ROUTE)

    def test_geometry_fallback_lists_animation_and_morph_losses(self) -> None:
        decision = decide_glb_character_route(
            source_skin_count=0, source_profile=None,
            source_animation_count=2, source_morph_target_count=4,
        )
        self.assertEqual(decision.losses, ("source animation clips", "morph targets"))

    def test_negative_skin_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "skin count"):
            decide_glb_character_route(
                source_skin_count=-1,
                source_profile=None,
            )


if __name__ == "__main__":
    unittest.main()
