"""Pure tests for end-to-end character benchmark support."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.glb_v2_character_support import assert_unrigged_mesh, normalized_landmarks


class GLBV2CharacterSupportTests(unittest.TestCase):
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
