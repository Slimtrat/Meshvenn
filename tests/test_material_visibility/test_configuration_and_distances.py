from __future__ import annotations

import math
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from core.material_visibility import DEFAULT_ABSOLUTE_EPSILON, DEFAULT_RAY_LENGTH_MULTIPLIER, DEFAULT_RELATIVE_EPSILON, MeshVisibilityTester, RaycastHit, VisibilityConfig, bounding_box_diagonal, compute_ray_distance, compute_surface_epsilon
from .helpers import RecordingRaycast, assert_vector_almost_equal

class VisibilityConfigTests(unittest.TestCase):

    def test_default_configuration_is_valid(self) -> None:
        config = VisibilityConfig()
        config.validate()
        self.assertEqual(config.relative_epsilon, DEFAULT_RELATIVE_EPSILON)
        self.assertEqual(config.absolute_epsilon, DEFAULT_ABSOLUTE_EPSILON)
        self.assertEqual(config.ray_length_multiplier, DEFAULT_RAY_LENGTH_MULTIPLIER)

    def test_zero_relative_epsilon_is_allowed(self) -> None:
        config = VisibilityConfig(relative_epsilon=0.0, absolute_epsilon=1e-06, ray_length_multiplier=2.0)
        config.validate()

    def test_negative_relative_epsilon_is_rejected(self) -> None:
        config = VisibilityConfig(relative_epsilon=-1e-05)
        with self.assertRaises(ValueError):
            config.validate()

    def test_zero_absolute_epsilon_is_rejected(self) -> None:
        config = VisibilityConfig(absolute_epsilon=0.0)
        with self.assertRaises(ValueError):
            config.validate()

    def test_negative_absolute_epsilon_is_rejected(self) -> None:
        config = VisibilityConfig(absolute_epsilon=-1e-06)
        with self.assertRaises(ValueError):
            config.validate()

    def test_ray_multiplier_must_be_greater_than_one(self) -> None:
        for multiplier in (-1.0, 0.0, 0.5, 1.0):
            with self.subTest(multiplier=multiplier):
                config = VisibilityConfig(ray_length_multiplier=multiplier)
                with self.assertRaises(ValueError):
                    config.validate()

    def test_non_finite_values_are_rejected(self) -> None:
        configs = [VisibilityConfig(relative_epsilon=math.inf), VisibilityConfig(relative_epsilon=math.nan), VisibilityConfig(absolute_epsilon=math.inf), VisibilityConfig(absolute_epsilon=math.nan), VisibilityConfig(ray_length_multiplier=math.inf), VisibilityConfig(ray_length_multiplier=math.nan)]
        for config in configs:
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    config.validate()

class BoundingBoxTests(unittest.TestCase):

    def test_diagonal_for_known_box(self) -> None:
        diagonal = bounding_box_diagonal([(0.0, 0.0, 0.0), (3.0, 4.0, 12.0)])
        self.assertAlmostEqual(diagonal, 13.0)

    def test_diagonal_supports_negative_coordinates(self) -> None:
        diagonal = bounding_box_diagonal([(-1.0, -2.0, -3.0), (1.0, 2.0, 3.0)])
        expected = math.sqrt(2.0 ** 2 + 4.0 ** 2 + 6.0 ** 2)
        self.assertAlmostEqual(diagonal, expected)

    def test_diagonal_uses_all_vertices(self) -> None:
        diagonal = bounding_box_diagonal([(0.0, 0.0, 0.0), (1.0, 50.0, 1.0), (10.0, 1.0, 20.0), (-5.0, -10.0, -2.0)])
        expected = math.sqrt(15.0 ** 2 + 60.0 ** 2 + 22.0 ** 2)
        self.assertAlmostEqual(diagonal, expected)

    def test_single_vertex_has_zero_diagonal(self) -> None:
        diagonal = bounding_box_diagonal([(5.0, -3.0, 8.0)])
        self.assertEqual(diagonal, 0.0)

    def test_empty_vertices_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            bounding_box_diagonal([])

    def test_non_finite_vertex_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            bounding_box_diagonal([(0.0, math.inf, 0.0)])

class VisibilityDistanceTests(unittest.TestCase):

    def test_relative_epsilon_scales_with_mesh(self) -> None:
        config = VisibilityConfig(relative_epsilon=0.01, absolute_epsilon=0.001)
        result = compute_surface_epsilon(10.0, config)
        self.assertAlmostEqual(result, 0.1)

    def test_absolute_epsilon_is_minimum(self) -> None:
        config = VisibilityConfig(relative_epsilon=1e-06, absolute_epsilon=0.01)
        result = compute_surface_epsilon(10.0, config)
        self.assertEqual(result, 0.01)

    def test_zero_size_mesh_uses_absolute_epsilon(self) -> None:
        config = VisibilityConfig(relative_epsilon=0.01, absolute_epsilon=0.002)
        result = compute_surface_epsilon(0.0, config)
        self.assertEqual(result, 0.002)

    def test_ray_distance_uses_mesh_diagonal(self) -> None:
        config = VisibilityConfig(ray_length_multiplier=3.0)
        result = compute_ray_distance(mesh_diagonal=4.0, surface_epsilon=0.001, config=config)
        self.assertAlmostEqual(result, 12.0)

    def test_ray_distance_stays_valid_for_tiny_mesh(self) -> None:
        config = VisibilityConfig(ray_length_multiplier=2.0)
        result = compute_ray_distance(mesh_diagonal=0.0, surface_epsilon=0.01, config=config)
        self.assertGreaterEqual(result, 0.1)

    def test_negative_mesh_diagonal_is_rejected(self) -> None:
        config = VisibilityConfig()
        with self.assertRaises(ValueError):
            compute_surface_epsilon(-1.0, config)
        with self.assertRaises(ValueError):
            compute_ray_distance(mesh_diagonal=-1.0, surface_epsilon=0.01, config=config)

    def test_invalid_surface_epsilon_is_rejected(self) -> None:
        config = VisibilityConfig()
        for epsilon in (-1.0, 0.0, math.inf, math.nan):
            with self.subTest(epsilon=epsilon):
                with self.assertRaises(ValueError):
                    compute_ray_distance(mesh_diagonal=1.0, surface_epsilon=epsilon, config=config)
