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


class GeometrySurfaceOutputTests(unittest.TestCase):

    def test_generic_geometry_output(self) -> None:
        output = geometry_output()
        self.assertEqual(output.implementation_id, "sdf-reconstruction-v1")
        self.assertEqual(output.width, 32)
        self.assertEqual(output.depth, 48)
        self.assertEqual(output.height, 64)
        self.assertAlmostEqual(output.voxel_size, 0.5)
        self.assertTrue(output.center_xy)

    def test_projection_dimensions_proxy(self) -> None:
        output = geometry_output(width=12, depth=13, height=14)
        self.assertEqual(output.projection_dimensions, (12, 13, 14))

    def test_projection_kwargs_proxy(self) -> None:
        output = geometry_output(
            width=12, depth=13, height=14, voxel_size=2.0, center_xy=False
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

    def test_object_name(self) -> None:
        obj = FakeBlenderObject(name="SDFSurface")
        output = GeometrySurfaceOutput(
            blender_object=obj,
            source=object(),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
        )
        self.assertEqual(output.object_name, "SDFSurface")

    def test_object_name_falls_back_to_type(self) -> None:

        class AnonymousObject:
            pass

        output = GeometrySurfaceOutput(
            blender_object=AnonymousObject(),
            source=object(),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
        )
        self.assertEqual(output.object_name, "AnonymousObject")

    def test_vertex_count_from_object(self) -> None:
        output = GeometrySurfaceOutput(
            blender_object=FakeBlenderObject(vertex_count=7, polygon_count=3),
            source=object(),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
        )
        self.assertEqual(output.vertex_count, 7)

    def test_polygon_count_from_object(self) -> None:
        output = GeometrySurfaceOutput(
            blender_object=FakeBlenderObject(vertex_count=7, polygon_count=3),
            source=object(),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
        )
        self.assertEqual(output.polygon_count, 3)

    def test_metrics_override_object_counts(self) -> None:
        output = GeometrySurfaceOutput(
            blender_object=FakeBlenderObject(vertex_count=4, polygon_count=2),
            source=object(),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
            metrics={"vertex_count": 100, "polygon_count": 50},
        )
        self.assertEqual(output.vertex_count, 100)
        self.assertEqual(output.polygon_count, 50)

    def test_metrics_and_metadata_are_copied(self) -> None:
        metrics = {"vertex_count": 100}
        metadata = {"algorithm": "sdf"}
        output = GeometrySurfaceOutput(
            blender_object=FakeBlenderObject(),
            source=object(),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
            metrics=metrics,
            metadata=metadata,
        )
        metrics["vertex_count"] = 999
        metadata["algorithm"] = "changed"
        self.assertEqual(output.metrics["vertex_count"], 100)
        self.assertEqual(output.metadata["algorithm"], "sdf")

    def test_mapping_keys_are_normalized_to_strings(self) -> None:
        output = GeometrySurfaceOutput(
            blender_object=FakeBlenderObject(),
            source=object(),
            projection_space=projection_space(),
            implementation_id="sdf-reconstruction-v1",
            metrics={123: "value"},
        )
        self.assertIn("123", output.metrics)
        self.assertEqual(output.metrics["123"], "value")

    def test_empty_mapping_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometrySurfaceOutput(
                blender_object=FakeBlenderObject(),
                source=object(),
                projection_space=projection_space(),
                implementation_id="sdf-reconstruction-v1",
                metadata={"": "invalid"},
            )

    def test_none_surface_object_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometrySurfaceOutput(
                blender_object=None,
                source=object(),
                projection_space=projection_space(),
                implementation_id="sdf-reconstruction-v1",
            )

    def test_none_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometrySurfaceOutput(
                blender_object=FakeBlenderObject(),
                source=None,
                projection_space=projection_space(),
                implementation_id="sdf-reconstruction-v1",
            )

    def test_invalid_projection_space_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            GeometrySurfaceOutput(
                blender_object=FakeBlenderObject(),
                source=object(),
                projection_space=object(),
                implementation_id="sdf-reconstruction-v1",
            )

    def test_invalid_implementation_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeometrySurfaceOutput(
                blender_object=FakeBlenderObject(),
                source=object(),
                projection_space=projection_space(),
                implementation_id="SDF Reconstruction",
            )

    def test_geometry_output_is_frozen(self) -> None:
        output = geometry_output()
        with self.assertRaises(FrozenInstanceError):
            output.implementation_id = "something-else"
