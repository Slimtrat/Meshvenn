from __future__ import annotations

import math
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from core.material_visibility import DEFAULT_ABSOLUTE_EPSILON, DEFAULT_RAY_LENGTH_MULTIPLIER, DEFAULT_RELATIVE_EPSILON, MeshVisibilityTester, RaycastHit, VisibilityConfig, bounding_box_diagonal, compute_ray_distance, compute_surface_epsilon

class RecordingRaycast:
    """
    Small deterministic raycast fake.

    Tests can configure one result and inspect the exact ray
    submitted by MeshVisibilityTester.
    """

    def __init__(self, result: RaycastHit | None=None) -> None:
        self.result = result
        self.calls: list[tuple[tuple[float, float, float], tuple[float, float, float], float]] = []

    def __call__(self, origin: tuple[float, float, float], direction: tuple[float, float, float], distance: float) -> RaycastHit | None:
        self.calls.append((origin, direction, distance))
        return self.result

def assert_vector_almost_equal(testcase: unittest.TestCase, actual: tuple[float, float, float], expected: tuple[float, float, float], *, places: int=7) -> None:
    testcase.assertEqual(len(actual), 3)
    testcase.assertEqual(len(expected), 3)
    for actual_component, expected_component in zip(actual, expected):
        testcase.assertAlmostEqual(actual_component, expected_component, places=places)
