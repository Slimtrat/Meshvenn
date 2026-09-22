from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from core.geometry_contracts import (
    DEFAULT_PROJECTION_CONVENTION,
    GeometryProjectionConvention,
    GeometryProjectionSpace,
    GeometrySurfaceOutput,
    require_geometry_surface_output,
    validate_geometry_surface_output,
)
from core.pipeline_contracts import PipelineContext, PipelineStage
from tests.geometry_contracts_test_support import (
    FakeBlenderObject,
    FakeSDFGeometryOutput,
    geometry_output,
    projection_space,
)


class GeometryProjectionConventionTests(unittest.TestCase):

    def test_default_convention_is_surface_envelope_v1(self) -> None:
        self.assertEqual(
            DEFAULT_PROJECTION_CONVENTION,
            GeometryProjectionConvention.SURFACE_ENVELOPE_V1,
        )
        self.assertEqual(DEFAULT_PROJECTION_CONVENTION.value, "surface-envelope-v1")


class GeometryProjectionSpaceTests(unittest.TestCase):

    def test_valid_projection_space(self) -> None:
        space = projection_space()
        self.assertEqual(space.width, 32)
        self.assertEqual(space.depth, 48)
        self.assertEqual(space.height, 64)
        self.assertAlmostEqual(space.voxel_size, 0.5)
        self.assertTrue(space.center_xy)
        self.assertEqual(
            space.convention, GeometryProjectionConvention.SURFACE_ENVELOPE_V1
        )

    def test_dimensions_tuple(self) -> None:
        space = projection_space(width=10, depth=20, height=30)
        self.assertEqual(space.dimensions, (10, 20, 30))

    def test_voxel_count(self) -> None:
        space = projection_space(width=4, depth=5, height=6)
        self.assertEqual(space.voxel_count, 120)

    def test_physical_dimensions(self) -> None:
        space = projection_space(width=10, depth=20, height=30, voxel_size=0.25)
        self.assertAlmostEqual(space.physical_width, 2.5)
        self.assertAlmostEqual(space.physical_depth, 5.0)
        self.assertAlmostEqual(space.physical_height, 7.5)
        self.assertEqual(space.physical_dimensions, (2.5, 5.0, 7.5))

    def test_centered_local_bounds(self) -> None:
        space = projection_space(
            width=10, depth=20, height=30, voxel_size=0.5, center_xy=True
        )
        self.assertEqual(space.minimum_local_point, (-2.5, -5.0, 0.0))
        self.assertEqual(space.maximum_local_point, (2.5, 5.0, 15.0))
        self.assertEqual(space.local_bounds, ((-2.5, -5.0, 0.0), (2.5, 5.0, 15.0)))

    def test_non_centered_local_bounds(self) -> None:
        space = projection_space(
            width=10, depth=20, height=30, voxel_size=0.5, center_xy=False
        )
        self.assertEqual(space.minimum_local_point, (0.0, 0.0, 0.0))
        self.assertEqual(space.maximum_local_point, (5.0, 10.0, 15.0))

    def test_projection_kwargs_match_projected_material_contract(self) -> None:
        space = projection_space(
            width=12, depth=24, height=36, voxel_size=0.75, center_xy=True
        )
        self.assertEqual(
            space.as_projection_kwargs(),
            {
                "width": 12,
                "depth": 24,
                "height": 36,
                "voxel_size": 0.75,
                "center_xy": True,
            },
        )

    def test_string_convention_is_normalized(self) -> None:
        space = GeometryProjectionSpace(
            width=8, depth=8, height=8, convention="surface-envelope-v1"
        )
        self.assertEqual(
            space.convention, GeometryProjectionConvention.SURFACE_ENVELOPE_V1
        )

    def test_zero_dimensions_are_rejected(self) -> None:
        cases = (
            {"width": 0, "depth": 2, "height": 2},
            {"width": 2, "depth": 0, "height": 2},
            {"width": 2, "depth": 2, "height": 0},
        )
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    GeometryProjectionSpace(**values)

    def test_negative_dimensions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=-1, depth=2, height=2)

    def test_boolean_dimension_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=True, depth=2, height=2)

    def test_float_dimension_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=2.5, depth=2, height=2)

    def test_zero_voxel_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=2, depth=2, height=2, voxel_size=0.0)

    def test_negative_voxel_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=2, depth=2, height=2, voxel_size=-1.0)

    def test_nan_voxel_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=2, depth=2, height=2, voxel_size=math.nan)

    def test_infinite_voxel_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=2, depth=2, height=2, voxel_size=math.inf)

    def test_unknown_projection_convention_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometryProjectionSpace(width=2, depth=2, height=2, convention="unknown")

    def test_projection_space_is_frozen(self) -> None:
        space = projection_space()
        with self.assertRaises(FrozenInstanceError):
            space.width = 100
