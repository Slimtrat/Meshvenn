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
from core.pipeline_contracts import (
    PipelineContext,
    PipelineStage,
)


# =========================================================
# Fake geometry objects
# =========================================================

class FakeMeshData:
    def __init__(
        self,
        *,
        vertex_count: int = 4,
        polygon_count: int = 2,
    ) -> None:
        self.vertices = [
            object()
            for _ in range(
                vertex_count
            )
        ]

        self.polygons = [
            object()
            for _ in range(
                polygon_count
            )
        ]


class FakeBlenderObject:
    def __init__(
        self,
        *,
        name: str = "FakeGeometry",
        vertex_count: int = 4,
        polygon_count: int = 2,
    ) -> None:
        self.name = name

        self.type = "MESH"

        self.data = FakeMeshData(
            vertex_count=vertex_count,
            polygon_count=polygon_count,
        )


class FakeSDFGeometryOutput(
    GeometrySurfaceOutput
):
    """
    Deliberately NOT a NativeVisualHullOutput.

    This represents the kind of subtype a future
    sdf-reconstruction-v1 implementation will return.
    """

    pass


# =========================================================
# Helpers
# =========================================================

def projection_space(
    *,
    width: int = 32,
    depth: int = 48,
    height: int = 64,
    voxel_size: float = 0.5,
    center_xy: bool = True,
) -> GeometryProjectionSpace:
    return GeometryProjectionSpace(
        width=width,
        depth=depth,
        height=height,
        voxel_size=voxel_size,
        center_xy=center_xy,
    )


def geometry_output(
    *,
    implementation_id: str = (
        "sdf-reconstruction-v1"
    ),
    width: int = 32,
    depth: int = 48,
    height: int = 64,
    voxel_size: float = 0.5,
    center_xy: bool = True,
    metrics=None,
    metadata=None,
) -> GeometrySurfaceOutput:
    source = SimpleNamespace(
        material_views=(
            "front",
            "side",
        )
    )

    return GeometrySurfaceOutput(
        blender_object=(
            FakeBlenderObject()
        ),

        source=source,

        projection_space=(
            projection_space(
                width=width,
                depth=depth,
                height=height,
                voxel_size=voxel_size,
                center_xy=center_xy,
            )
        ),

        implementation_id=(
            implementation_id
        ),

        metrics=(
            metrics
            or {}
        ),

        metadata=(
            metadata
            or {}
        ),
    )


# =========================================================
# GeometryProjectionConvention
# =========================================================

class GeometryProjectionConventionTests(
    unittest.TestCase
):
    def test_default_convention_is_surface_envelope_v1(
        self,
    ) -> None:
        self.assertEqual(
            DEFAULT_PROJECTION_CONVENTION,
            (
                GeometryProjectionConvention
                .SURFACE_ENVELOPE_V1
            ),
        )

        self.assertEqual(
            DEFAULT_PROJECTION_CONVENTION.value,
            "surface-envelope-v1",
        )


# =========================================================
# GeometryProjectionSpace
# =========================================================

class GeometryProjectionSpaceTests(
    unittest.TestCase
):
    def test_valid_projection_space(
        self,
    ) -> None:
        space = projection_space()

        self.assertEqual(
            space.width,
            32,
        )

        self.assertEqual(
            space.depth,
            48,
        )

        self.assertEqual(
            space.height,
            64,
        )

        self.assertAlmostEqual(
            space.voxel_size,
            0.5,
        )

        self.assertTrue(
            space.center_xy
        )

        self.assertEqual(
            space.convention,
            (
                GeometryProjectionConvention
                .SURFACE_ENVELOPE_V1
            ),
        )

    def test_dimensions_tuple(
        self,
    ) -> None:
        space = projection_space(
            width=10,
            depth=20,
            height=30,
        )

        self.assertEqual(
            space.dimensions,
            (
                10,
                20,
                30,
            ),
        )

    def test_voxel_count(
        self,
    ) -> None:
        space = projection_space(
            width=4,
            depth=5,
            height=6,
        )

        self.assertEqual(
            space.voxel_count,
            120,
        )

    def test_physical_dimensions(
        self,
    ) -> None:
        space = projection_space(
            width=10,
            depth=20,
            height=30,
            voxel_size=0.25,
        )

        self.assertAlmostEqual(
            space.physical_width,
            2.5,
        )

        self.assertAlmostEqual(
            space.physical_depth,
            5.0,
        )

        self.assertAlmostEqual(
            space.physical_height,
            7.5,
        )

        self.assertEqual(
            space.physical_dimensions,
            (
                2.5,
                5.0,
                7.5,
            ),
        )

    def test_centered_local_bounds(
        self,
    ) -> None:
        space = projection_space(
            width=10,
            depth=20,
            height=30,
            voxel_size=0.5,
            center_xy=True,
        )

        self.assertEqual(
            space.minimum_local_point,
            (
                -2.5,
                -5.0,
                0.0,
            ),
        )

        self.assertEqual(
            space.maximum_local_point,
            (
                2.5,
                5.0,
                15.0,
            ),
        )

        self.assertEqual(
            space.local_bounds,
            (
                (
                    -2.5,
                    -5.0,
                    0.0,
                ),
                (
                    2.5,
                    5.0,
                    15.0,
                ),
            ),
        )

    def test_non_centered_local_bounds(
        self,
    ) -> None:
        space = projection_space(
            width=10,
            depth=20,
            height=30,
            voxel_size=0.5,
            center_xy=False,
        )

        self.assertEqual(
            space.minimum_local_point,
            (
                0.0,
                0.0,
                0.0,
            ),
        )

        self.assertEqual(
            space.maximum_local_point,
            (
                5.0,
                10.0,
                15.0,
            ),
        )

    def test_projection_kwargs_match_projected_material_contract(
        self,
    ) -> None:
        space = projection_space(
            width=12,
            depth=24,
            height=36,
            voxel_size=0.75,
            center_xy=True,
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

    def test_string_convention_is_normalized(
        self,
    ) -> None:
        space = GeometryProjectionSpace(
            width=8,
            depth=8,
            height=8,
            convention=(
                "surface-envelope-v1"
            ),
        )

        self.assertEqual(
            space.convention,
            (
                GeometryProjectionConvention
                .SURFACE_ENVELOPE_V1
            ),
        )

    def test_zero_dimensions_are_rejected(
        self,
    ) -> None:
        cases = (
            {
                "width": 0,
                "depth": 2,
                "height": 2,
            },
            {
                "width": 2,
                "depth": 0,
                "height": 2,
            },
            {
                "width": 2,
                "depth": 2,
                "height": 0,
            },
        )

        for values in cases:
            with self.subTest(
                values=values
            ):
                with self.assertRaises(
                    ValueError
                ):
                    GeometryProjectionSpace(
                        **values
                    )

    def test_negative_dimensions_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=-1,
                depth=2,
                height=2,
            )

    def test_boolean_dimension_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=True,
                depth=2,
                height=2,
            )

    def test_float_dimension_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=2.5,
                depth=2,
                height=2,
            )

    def test_zero_voxel_size_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=2,
                depth=2,
                height=2,
                voxel_size=0.0,
            )

    def test_negative_voxel_size_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=2,
                depth=2,
                height=2,
                voxel_size=-1.0,
            )

    def test_nan_voxel_size_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=2,
                depth=2,
                height=2,
                voxel_size=math.nan,
            )

    def test_infinite_voxel_size_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=2,
                depth=2,
                height=2,
                voxel_size=math.inf,
            )

    def test_unknown_projection_convention_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometryProjectionSpace(
                width=2,
                depth=2,
                height=2,
                convention="unknown",
            )

    def test_projection_space_is_frozen(
        self,
    ) -> None:
        space = projection_space()

        with self.assertRaises(
            FrozenInstanceError
        ):
            space.width = 100


# =========================================================
# GeometrySurfaceOutput
# =========================================================

class GeometrySurfaceOutputTests(
    unittest.TestCase
):
    def test_generic_geometry_output(
        self,
    ) -> None:
        output = geometry_output()

        self.assertEqual(
            output.implementation_id,
            "sdf-reconstruction-v1",
        )

        self.assertEqual(
            output.width,
            32,
        )

        self.assertEqual(
            output.depth,
            48,
        )

        self.assertEqual(
            output.height,
            64,
        )

        self.assertAlmostEqual(
            output.voxel_size,
            0.5,
        )

        self.assertTrue(
            output.center_xy
        )

    def test_projection_dimensions_proxy(
        self,
    ) -> None:
        output = geometry_output(
            width=12,
            depth=13,
            height=14,
        )

        self.assertEqual(
            output.projection_dimensions,
            (
                12,
                13,
                14,
            ),
        )

    def test_projection_kwargs_proxy(
        self,
    ) -> None:
        output = geometry_output(
            width=12,
            depth=13,
            height=14,
            voxel_size=2.0,
            center_xy=False,
        )

        self.assertEqual(
            output.projection_kwargs(),
            {
                "width": 12,
                "depth": 13,
                "height": 14,
                "voxel_size": 2.0,
                "center_xy": False,
            },
        )

    def test_object_name(
        self,
    ) -> None:
        obj = FakeBlenderObject(
            name="SDFSurface"
        )

        output = GeometrySurfaceOutput(
            blender_object=obj,
            source=object(),
            projection_space=(
                projection_space()
            ),
            implementation_id=(
                "sdf-reconstruction-v1"
            ),
        )

        self.assertEqual(
            output.object_name,
            "SDFSurface",
        )

    def test_object_name_falls_back_to_type(
        self,
    ) -> None:
        class AnonymousObject:
            pass

        output = GeometrySurfaceOutput(
            blender_object=(
                AnonymousObject()
            ),
            source=object(),
            projection_space=(
                projection_space()
            ),
            implementation_id=(
                "sdf-reconstruction-v1"
            ),
        )

        self.assertEqual(
            output.object_name,
            "AnonymousObject",
        )

    def test_vertex_count_from_object(
        self,
    ) -> None:
        output = GeometrySurfaceOutput(
            blender_object=(
                FakeBlenderObject(
                    vertex_count=7,
                    polygon_count=3,
                )
            ),
            source=object(),
            projection_space=(
                projection_space()
            ),
            implementation_id=(
                "sdf-reconstruction-v1"
            ),
        )

        self.assertEqual(
            output.vertex_count,
            7,
        )

    def test_polygon_count_from_object(
        self,
    ) -> None:
        output = GeometrySurfaceOutput(
            blender_object=(
                FakeBlenderObject(
                    vertex_count=7,
                    polygon_count=3,
                )
            ),
            source=object(),
            projection_space=(
                projection_space()
            ),
            implementation_id=(
                "sdf-reconstruction-v1"
            ),
        )

        self.assertEqual(
            output.polygon_count,
            3,
        )

    def test_metrics_override_object_counts(
        self,
    ) -> None:
        output = GeometrySurfaceOutput(
            blender_object=(
                FakeBlenderObject(
                    vertex_count=4,
                    polygon_count=2,
                )
            ),
            source=object(),
            projection_space=(
                projection_space()
            ),
            implementation_id=(
                "sdf-reconstruction-v1"
            ),
            metrics={
                "vertex_count": 100,
                "polygon_count": 50,
            },
        )

        self.assertEqual(
            output.vertex_count,
            100,
        )

        self.assertEqual(
            output.polygon_count,
            50,
        )

    def test_metrics_and_metadata_are_copied(
        self,
    ) -> None:
        metrics = {
            "vertex_count": 100,
        }

        metadata = {
            "algorithm": "sdf",
        }

        output = GeometrySurfaceOutput(
            blender_object=(
                FakeBlenderObject()
            ),
            source=object(),
            projection_space=(
                projection_space()
            ),
            implementation_id=(
                "sdf-reconstruction-v1"
            ),
            metrics=metrics,
            metadata=metadata,
        )

        metrics[
            "vertex_count"
        ] = 999

        metadata[
            "algorithm"
        ] = "changed"

        self.assertEqual(
            output.metrics[
                "vertex_count"
            ],
            100,
        )

        self.assertEqual(
            output.metadata[
                "algorithm"
            ],
            "sdf",
        )

    def test_mapping_keys_are_normalized_to_strings(
        self,
    ) -> None:
        output = GeometrySurfaceOutput(
            blender_object=(
                FakeBlenderObject()
            ),
            source=object(),
            projection_space=(
                projection_space()
            ),
            implementation_id=(
                "sdf-reconstruction-v1"
            ),
            metrics={
                123: "value",
            },
        )

        self.assertIn(
            "123",
            output.metrics,
        )

        self.assertEqual(
            output.metrics[
                "123"
            ],
            "value",
        )

    def test_empty_mapping_key_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometrySurfaceOutput(
                blender_object=(
                    FakeBlenderObject()
                ),
                source=object(),
                projection_space=(
                    projection_space()
                ),
                implementation_id=(
                    "sdf-reconstruction-v1"
                ),
                metadata={
                    "": "invalid",
                },
            )

    def test_none_surface_object_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometrySurfaceOutput(
                blender_object=None,
                source=object(),
                projection_space=(
                    projection_space()
                ),
                implementation_id=(
                    "sdf-reconstruction-v1"
                ),
            )

    def test_none_source_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometrySurfaceOutput(
                blender_object=(
                    FakeBlenderObject()
                ),
                source=None,
                projection_space=(
                    projection_space()
                ),
                implementation_id=(
                    "sdf-reconstruction-v1"
                ),
            )

    def test_invalid_projection_space_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            GeometrySurfaceOutput(
                blender_object=(
                    FakeBlenderObject()
                ),
                source=object(),
                projection_space=object(),
                implementation_id=(
                    "sdf-reconstruction-v1"
                ),
            )

    def test_invalid_implementation_id_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            GeometrySurfaceOutput(
                blender_object=(
                    FakeBlenderObject()
                ),
                source=object(),
                projection_space=(
                    projection_space()
                ),
                implementation_id=(
                    "SDF Reconstruction"
                ),
            )

    def test_geometry_output_is_frozen(
        self,
    ) -> None:
        output = geometry_output()

        with self.assertRaises(
            FrozenInstanceError
        ):
            output.implementation_id = (
                "something-else"
            )


# =========================================================
# Future implementation compatibility
# =========================================================

class GeometryImplementationCompatibilityTests(
    unittest.TestCase
):
    def test_non_visual_hull_subclass_is_valid(
        self,
    ) -> None:
        output = FakeSDFGeometryOutput(
            blender_object=(
                FakeBlenderObject(
                    name="FakeSDF"
                )
            ),

            source=SimpleNamespace(
                material_views=(
                    "front",
                    "side",
                )
            ),

            projection_space=(
                projection_space()
            ),

            implementation_id=(
                "sdf-reconstruction-v1"
            ),

            metrics={
                "vertex_count": 1200,
                "polygon_count": 1100,
            },

            metadata={
                "field": "signed-distance",
            },
        )

        validated = (
            validate_geometry_surface_output(
                output
            )
        )

        self.assertIs(
            validated,
            output,
        )

        self.assertIsInstance(
            validated,
            GeometrySurfaceOutput,
        )

        self.assertEqual(
            validated.implementation_id,
            "sdf-reconstruction-v1",
        )

        self.assertEqual(
            validated.vertex_count,
            1200,
        )

        self.assertEqual(
            validated.polygon_count,
            1100,
        )

    def test_context_accepts_generic_sdf_geometry(
        self,
    ) -> None:
        context = PipelineContext()

        output = FakeSDFGeometryOutput(
            blender_object=(
                FakeBlenderObject(
                    name="FutureSDF"
                )
            ),

            source=SimpleNamespace(
                material_views=(
                    "front",
                    "right",
                )
            ),

            projection_space=(
                projection_space(
                    width=64,
                    depth=64,
                    height=96,
                    voxel_size=1.0,
                )
            ),

            implementation_id=(
                "sdf-reconstruction-v1"
            ),
        )

        context.set_output(
            PipelineStage.GEOMETRY,
            output,
        )

        resolved = (
            require_geometry_surface_output(
                context
            )
        )

        self.assertIs(
            resolved,
            output,
        )

        self.assertEqual(
            resolved.implementation_id,
            "sdf-reconstruction-v1",
        )

        self.assertEqual(
            resolved.projection_dimensions,
            (
                64,
                64,
                96,
            ),
        )

    def test_context_rejects_old_untyped_geometry(
        self,
    ) -> None:
        context = PipelineContext()

        context.set_output(
            PipelineStage.GEOMETRY,
            SimpleNamespace(
                blender_object=(
                    FakeBlenderObject()
                )
            ),
        )

        with self.assertRaises(
            TypeError
        ):
            require_geometry_surface_output(
                context
            )

    def test_context_requires_geometry_output(
        self,
    ) -> None:
        context = PipelineContext()

        with self.assertRaises(
            RuntimeError
        ):
            require_geometry_surface_output(
                context
            )


# =========================================================
# Contract regression
# =========================================================

class GeometryContractRegressionTests(
    unittest.TestCase
):
    def test_projection_space_matches_historical_surface_envelope(
        self,
    ) -> None:
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
            width=10,
            depth=20,
            height=30,
            voxel_size=0.5,
            center_xy=True,
        )

        self.assertEqual(
            space.local_bounds,
            (
                (
                    -2.5,
                    -5.0,
                    0.0,
                ),
                (
                    2.5,
                    5.0,
                    15.0,
                ),
            ),
        )

    def test_projection_kwargs_are_algorithm_neutral(
        self,
    ) -> None:
        visual_hull = geometry_output(
            implementation_id=(
                "native-visual-hull"
            )
        )

        sdf = geometry_output(
            implementation_id=(
                "sdf-reconstruction-v1"
            )
        )

        self.assertEqual(
            visual_hull
            .projection_kwargs(),
            sdf
            .projection_kwargs(),
        )

    def test_generic_geometry_does_not_require_native_fields(
        self,
    ) -> None:
        output = geometry_output()

        self.assertFalse(
            hasattr(
                output,
                "volume",
            )
        )

        self.assertFalse(
            hasattr(
                output,
                "native_mesh",
            )
        )

        self.assertEqual(
            output.implementation_id,
            "sdf-reconstruction-v1",
        )


# =========================================================
# Entry point
# =========================================================

if __name__ == "__main__":
    unittest.main()