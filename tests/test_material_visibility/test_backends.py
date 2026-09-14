from __future__ import annotations

import math
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from core.material_visibility import DEFAULT_ABSOLUTE_EPSILON, DEFAULT_RAY_LENGTH_MULTIPLIER, DEFAULT_RELATIVE_EPSILON, MeshVisibilityTester, RaycastHit, VisibilityConfig, bounding_box_diagonal, compute_ray_distance, compute_surface_epsilon
from .helpers import RecordingRaycast, assert_vector_almost_equal

class RaycastBackendTests(unittest.TestCase):

    def test_hit_beyond_requested_distance_is_ignored(self) -> None:
        raycast = RecordingRaycast(RaycastHit(distance=100.0))
        tester = MeshVisibilityTester(raycast, surface_epsilon=0.1, max_distance=5.0)
        result = tester.query((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        self.assertTrue(result.visible)

    def test_negative_hit_distance_is_rejected(self) -> None:
        tester = MeshVisibilityTester(RecordingRaycast(RaycastHit(distance=-1.0)), surface_epsilon=0.01, max_distance=5.0)
        with self.assertRaises(ValueError):
            tester.query((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))

    def test_non_finite_hit_distance_is_rejected(self) -> None:
        for distance in (math.inf, math.nan):
            with self.subTest(distance=distance):
                tester = MeshVisibilityTester(RecordingRaycast(RaycastHit(distance=distance)), surface_epsilon=0.01, max_distance=5.0)
                with self.assertRaises(ValueError):
                    tester.query((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))

class BlenderFactoryTests(unittest.TestCase):

    @staticmethod
    def _vertex(x: float, y: float, z: float):
        return SimpleNamespace(co=SimpleNamespace(x=x, y=y, z=z))

    @staticmethod
    def _mesh_object():
        mesh = SimpleNamespace(vertices=[BlenderFactoryTests._vertex(0.0, 0.0, 0.0), BlenderFactoryTests._vertex(3.0, 0.0, 0.0), BlenderFactoryTests._vertex(0.0, 4.0, 0.0)], polygons=[SimpleNamespace(vertices=(0, 1, 2))], update=MagicMock())
        return SimpleNamespace(type='MESH', data=mesh)

    def test_factory_builds_backend_from_local_mesh(self) -> None:
        obj = self._mesh_object()
        backend = RecordingRaycast()
        config = VisibilityConfig(relative_epsilon=0.01, absolute_epsilon=0.001, ray_length_multiplier=2.0)
        with patch('core.material_visibility._build_blender_bvh_raycast', return_value=backend) as build_backend:
            tester = MeshVisibilityTester.from_blender_object(obj, config=config)
        obj.data.update.assert_called_once_with()
        build_backend.assert_called_once_with([(0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, 4.0, 0.0)], [(0, 1, 2)])
        self.assertAlmostEqual(tester.surface_epsilon, 0.05)
        self.assertAlmostEqual(tester.max_distance, 10.0)

    def test_factory_result_is_immediately_usable(self) -> None:
        obj = self._mesh_object()
        backend = RecordingRaycast()
        with patch('core.material_visibility._build_blender_bvh_raycast', return_value=backend):
            tester = MeshVisibilityTester.from_blender_object(obj)
        visible = tester.is_visible((0.0, 0.0, 0.0), (0.0, -1.0, 0.0))
        self.assertTrue(visible)
        self.assertEqual(len(backend.calls), 1)

    def test_non_mesh_object_is_rejected(self) -> None:
        obj = SimpleNamespace(type='LIGHT', data=None)
        with self.assertRaises(TypeError):
            MeshVisibilityTester.from_blender_object(obj)

    def test_none_object_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            MeshVisibilityTester.from_blender_object(None)

    def test_object_without_mesh_data_is_rejected(self) -> None:
        obj = SimpleNamespace(type='MESH', data=None)
        with self.assertRaises(TypeError):
            MeshVisibilityTester.from_blender_object(obj)

    def test_empty_mesh_is_rejected(self) -> None:
        mesh = SimpleNamespace(vertices=[], polygons=[], update=MagicMock())
        obj = SimpleNamespace(type='MESH', data=mesh)
        with self.assertRaises(ValueError):
            MeshVisibilityTester.from_blender_object(obj)

    def test_mesh_without_polygons_is_rejected(self) -> None:
        mesh = SimpleNamespace(vertices=[self._vertex(0.0, 0.0, 0.0), self._vertex(1.0, 0.0, 0.0), self._vertex(0.0, 1.0, 0.0)], polygons=[], update=MagicMock())
        obj = SimpleNamespace(type='MESH', data=mesh)
        with self.assertRaises(ValueError):
            MeshVisibilityTester.from_blender_object(obj)

    def test_degenerate_polygon_is_ignored(self) -> None:
        mesh = SimpleNamespace(vertices=[self._vertex(0.0, 0.0, 0.0), self._vertex(1.0, 0.0, 0.0)], polygons=[SimpleNamespace(vertices=(0, 1))], update=MagicMock())
        obj = SimpleNamespace(type='MESH', data=mesh)
        with self.assertRaises(ValueError):
            MeshVisibilityTester.from_blender_object(obj)
