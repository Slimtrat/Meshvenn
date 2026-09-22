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


class GeometryImplementationCompatibilityTests(unittest.TestCase):

    def test_non_visual_hull_subclass_is_valid(self) -> None:
        output = FakeSDFGeometryOutput(
            blender_object=FakeBlenderObject(name="FakeSDF"),
            source=SimpleNamespace(material_views=("front", "side")),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
            metrics={"vertex_count": 1200, "polygon_count": 1100},
            metadata={"field": "signed-distance"},
        )
        validated = validate_geometry_surface_output(output)
        self.assertIs(validated, output)
        self.assertIsInstance(validated, GeometrySurfaceOutput)
        self.assertEqual(validated.implementation_id, "sdf-reconstruction-v1")
        self.assertEqual(validated.vertex_count, 1200)
        self.assertEqual(validated.polygon_count, 1100)

    def test_context_accepts_generic_sdf_geometry(self) -> None:
        context = PipelineContext()
        output = FakeSDFGeometryOutput(
            blender_object=FakeBlenderObject(name="FutureSDF"),
            source=SimpleNamespace(material_views=("front", "right")),
            projection_space=projection_space(
                width=64, depth=64, height=96, voxel_size=1.0
            ),
            implementation_id="sdf-reconstruction-v1",
        )
        context.set_output(PipelineStage.GEOMETRY, output)
        resolved = require_geometry_surface_output(context)
        self.assertIs(resolved, output)
        self.assertEqual(resolved.implementation_id, "sdf-reconstruction-v1")
        self.assertEqual(resolved.projection_dimensions, (64, 64, 96))

    def test_context_rejects_old_untyped_geometry(self) -> None:
        context = PipelineContext()
        context.set_output(
            PipelineStage.GEOMETRY, SimpleNamespace(blender_object=FakeBlenderObject())
        )
        with self.assertRaises(TypeError):
            require_geometry_surface_output(context)

    def test_context_requires_geometry_output(self) -> None:
        context = PipelineContext()
        with self.assertRaises(RuntimeError):
            require_geometry_surface_output(context)


class GeometryContractRegressionTests(unittest.TestCase):

    def test_projection_space_matches_historical_surface_envelope(self) -> None:
        """
        This locks the coordinate convention used by the
        existing projected material pipeline.

        With:

            width  = 10
            depth  = 20
            height = 30
            voxel  = 0.5
            center_xy = True

        local mesh envelope must be:

            X = -2.5 .. +2.5
            Y = -5.0 .. +5.0
            Z =  0.0 .. 15.0
        """
        space = GeometryProjectionSpace(
            width=10, depth=20, height=30, voxel_size=0.5, center_xy=True
        )
        self.assertEqual(space.local_bounds, ((-2.5, -5.0, 0.0), (2.5, 5.0, 15.0)))

    def test_projection_kwargs_are_algorithm_neutral(self) -> None:
        visual_hull = geometry_output(implementation_id="native-visual-hull")
        sdf = geometry_output(implementation_id="sdf-reconstruction-v1")
        self.assertEqual(visual_hull.projection_kwargs(), sdf.projection_kwargs())

    def test_generic_geometry_does_not_require_native_fields(self) -> None:
        output = geometry_output()
        self.assertFalse(hasattr(output, "volume"))
        self.assertFalse(hasattr(output, "native_mesh"))
        self.assertEqual(output.implementation_id, "sdf-reconstruction-v1")
