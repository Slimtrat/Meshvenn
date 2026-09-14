from __future__ import annotations

import math
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from core.material_visibility import DEFAULT_ABSOLUTE_EPSILON, DEFAULT_RAY_LENGTH_MULTIPLIER, DEFAULT_RELATIVE_EPSILON, MeshVisibilityTester, RaycastHit, VisibilityConfig, bounding_box_diagonal, compute_ray_distance, compute_surface_epsilon
from .helpers import RecordingRaycast, assert_vector_almost_equal

class VisibilityTesterConstructionTests(unittest.TestCase):

    def test_raycast_must_be_callable(self) -> None:
        with self.assertRaises(TypeError):
            MeshVisibilityTester(None, surface_epsilon=0.01, max_distance=10.0)

    def test_surface_epsilon_must_be_positive(self) -> None:
        for epsilon in (-1.0, 0.0, math.inf, math.nan):
            with self.subTest(epsilon=epsilon):
                with self.assertRaises(ValueError):
                    MeshVisibilityTester(RecordingRaycast(), surface_epsilon=epsilon, max_distance=10.0)

    def test_max_distance_must_exceed_epsilon(self) -> None:
        for distance in (-1.0, 0.0, 0.005, 0.01, math.inf, math.nan):
            with self.subTest(distance=distance):
                with self.assertRaises(ValueError):
                    MeshVisibilityTester(RecordingRaycast(), surface_epsilon=0.01, max_distance=distance)

class ClearVisibilityTests(unittest.TestCase):

    def test_no_hit_means_visible(self) -> None:
        raycast = RecordingRaycast(None)
        tester = MeshVisibilityTester(raycast, surface_epsilon=0.01, max_distance=10.0)
        result = tester.query((1.0, 2.0, 3.0), (0.0, -1.0, 0.0))
        self.assertTrue(result.visible)
        self.assertFalse(result.occluded)
        self.assertIsNone(result.hit_distance)
        self.assertIsNone(result.polygon_index)

    def test_ray_starts_offset_toward_camera(self) -> None:
        raycast = RecordingRaycast()
        tester = MeshVisibilityTester(raycast, surface_epsilon=0.25, max_distance=10.0)
        tester.query((1.0, 2.0, 3.0), (0.0, -1.0, 0.0))
        self.assertEqual(len(raycast.calls), 1)
        origin, direction, distance = raycast.calls[0]
        assert_vector_almost_equal(self, origin, (1.0, 1.75, 3.0))
        assert_vector_almost_equal(self, direction, (0.0, -1.0, 0.0))
        self.assertAlmostEqual(distance, 9.75)

    def test_camera_direction_is_normalized(self) -> None:
        raycast = RecordingRaycast()
        tester = MeshVisibilityTester(raycast, surface_epsilon=0.1, max_distance=5.0)
        tester.query((0.0, 0.0, 0.0), (0.0, -10.0, 0.0))
        origin, direction, _ = raycast.calls[0]
        assert_vector_almost_equal(self, direction, (0.0, -1.0, 0.0))
        assert_vector_almost_equal(self, origin, (0.0, -0.1, 0.0))

    def test_is_visible_shortcut_returns_true(self) -> None:
        tester = MeshVisibilityTester(RecordingRaycast(), surface_epsilon=0.01, max_distance=5.0)
        self.assertTrue(tester.is_visible((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))

class OcclusionTests(unittest.TestCase):

    def test_hit_between_surface_and_camera_blocks_view(self) -> None:
        hit = RaycastHit(distance=2.0, polygon_index=42, position=(0.0, -2.01, 0.0), normal=(0.0, 1.0, 0.0))
        raycast = RecordingRaycast(hit)
        tester = MeshVisibilityTester(raycast, surface_epsilon=0.01, max_distance=10.0)
        result = tester.query((0.0, 0.0, 0.0), (0.0, -1.0, 0.0))
        self.assertFalse(result.visible)
        self.assertTrue(result.occluded)
        self.assertEqual(result.hit_distance, 2.0)
        self.assertEqual(result.polygon_index, 42)

    def test_is_visible_shortcut_returns_false(self) -> None:
        tester = MeshVisibilityTester(RecordingRaycast(RaycastHit(distance=1.0)), surface_epsilon=0.01, max_distance=5.0)
        self.assertFalse(tester.is_visible((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))

class SelfIntersectionTests(unittest.TestCase):

    def test_zero_distance_hit_is_ignored(self) -> None:
        tester = MeshVisibilityTester(RecordingRaycast(RaycastHit(distance=0.0, polygon_index=3)), surface_epsilon=0.01, max_distance=5.0)
        result = tester.query((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        self.assertTrue(result.visible)
        self.assertFalse(result.occluded)

    def test_hit_inside_epsilon_is_ignored(self) -> None:
        tester = MeshVisibilityTester(RecordingRaycast(RaycastHit(distance=0.005)), surface_epsilon=0.01, max_distance=5.0)
        result = tester.query((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        self.assertTrue(result.visible)

    def test_hit_exactly_at_epsilon_is_ignored(self) -> None:
        tester = MeshVisibilityTester(RecordingRaycast(RaycastHit(distance=0.01)), surface_epsilon=0.01, max_distance=5.0)
        result = tester.query((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        self.assertTrue(result.visible)

    def test_hit_just_after_epsilon_blocks(self) -> None:
        tester = MeshVisibilityTester(RecordingRaycast(RaycastHit(distance=0.0101)), surface_epsilon=0.01, max_distance=5.0)
        result = tester.query((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        self.assertFalse(result.visible)
        self.assertTrue(result.occluded)

class VisibilityQueryValidationTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tester = MeshVisibilityTester(RecordingRaycast(), surface_epsilon=0.01, max_distance=5.0)

    def test_zero_camera_direction_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.tester.query((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    def test_non_finite_camera_direction_is_rejected(self) -> None:
        directions = [(math.inf, 0.0, 0.0), (math.nan, 1.0, 0.0)]
        for direction in directions:
            with self.subTest(direction=direction):
                with self.assertRaises(ValueError):
                    self.tester.query((0.0, 0.0, 0.0), direction)

    def test_non_finite_position_is_rejected(self) -> None:
        positions = [(math.inf, 0.0, 0.0), (0.0, math.nan, 0.0)]
        for position in positions:
            with self.subTest(position=position):
                with self.assertRaises(ValueError):
                    self.tester.query(position, (1.0, 0.0, 0.0))
