from __future__ import annotations

import math
import unittest

from array import array
from types import SimpleNamespace

from core.image_mask import (
    BinaryMask,
)
from core.projection_math import (
    NormalizedPoint,
)
from core.sdf import (
    DEFAULT_ISO_LEVEL,
    DEFAULT_SMOOTHNESS,
    DEFAULT_SURFACE_OFFSET,
    DEFAULT_SYMMETRY_X,
    SDFBuildConfig,
    SDFProjection,
    SDFVolume,
    SignedDistanceMask,
    build_sdf_from_views,
    build_sdf_projections,
    build_sdf_volume,
    build_signed_distance_mask,
    cubic_sdf_config,
    fuse_signed_distances,
    sample_fused_sdf,
    smooth_max,
)


# =========================================================
# Mask helpers
# =========================================================

def mask_from_rows(
    *rows: str,
) -> BinaryMask:
    """
    Build a BinaryMask from ASCII rows.

        # = foreground
        . = background

    Rows are given bottom-to-top exactly as BinaryMask stores
    them. For symmetric synthetic masks this distinction does
    not affect the tests, but keeping the representation
    explicit avoids hidden image-coordinate assumptions.
    """

    if not rows:
        raise ValueError(
            "At least one row is required."
        )

    width = len(
        rows[0]
    )

    if width <= 0:
        raise ValueError(
            "Rows cannot be empty."
        )

    for row in rows:
        if len(
            row
        ) != width:
            raise ValueError(
                (
                    "All mask rows must have "
                    "the same width."
                )
            )

    values = bytearray()

    for row in rows:
        for value in row:
            if value == "#":
                values.append(
                    1
                )

            elif value == ".":
                values.append(
                    0
                )

            else:
                raise ValueError(
                    (
                        "Unsupported mask character: "
                        f"{value!r}"
                    )
                )

    return BinaryMask(
        width=width,
        height=len(
            rows
        ),
        values=bytes(
            values
        ),
    )


def centered_single_pixel_mask() -> BinaryMask:
    return mask_from_rows(
        ".....",
        ".....",
        "..#..",
        ".....",
        ".....",
    )


def centered_square_mask() -> BinaryMask:
    return mask_from_rows(
        ".......",
        ".......",
        "..###..",
        "..###..",
        "..###..",
        ".......",
        ".......",
    )


def centered_large_square_mask() -> BinaryMask:
    return mask_from_rows(
        ".........",
        ".........",
        "..#####..",
        "..#####..",
        "..#####..",
        "..#####..",
        "..#####..",
        ".........",
        ".........",
    )


def centered_circle_mask(
    *,
    size: int =  nine,
    radius: float = 3.0,
) -> BinaryMask:
    center = (
        float(
            size - 1
        )
        * 0.5
    )

    values = bytearray()

    for y in range(
        size
    ):
        for x in range(
            size
        ):
            dx = (
                float(x)
                - center
            )

            dy = (
                float(y)
                - center
            )

            inside = (
                dx * dx
                + dy * dy
                <= radius * radius
            )

            values.append(
                1
                if inside
                else 0
            )

    return BinaryMask(
        width=size,
        height=size,
        values=bytes(
            values
        ),
    )


# Python has no `nine` constant; keeping construction
# explicit below avoids clever helpers becoming part of the
# test surface.
def circle_mask_9() -> BinaryMask:
    size = 9

    center = 4.0

    radius = 3.0

    values = bytearray()

    for y in range(
        size
    ):
        for x in range(
            size
        ):
            dx = (
                float(x)
                - center
            )

            dy = (
                float(y)
                - center
            )

            values.append(
                1
                if (
                    dx * dx
                    + dy * dy
                    <= radius * radius
                )
                else 0
            )

    return BinaryMask(
        width=size,
        height=size,
        values=bytes(
            values
        ),
    )


# =========================================================
# Signed-distance mask
# =========================================================

class SignedDistanceMaskTests(
    unittest.TestCase
):
    def test_single_pixel_exact_axis_distances(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_single_pixel_mask(),
                horizontal_extent=1.0,
                vertical_extent=1.0,
            )
        )

        # 5 samples span [-1, +1]:
        #
        #     spacing = 2 / 4 = 0.5

        self.assertAlmostEqual(
            field.horizontal_spacing,
            0.5,
        )

        self.assertAlmostEqual(
            field.vertical_spacing,
            0.5,
        )

        self.assertAlmostEqual(
            field.get(
                2,
                2,
            ),
            -0.5,
            places=6,
        )

        self.assertAlmostEqual(
            field.get(
                3,
                2,
            ),
            0.5,
            places=6,
        )

        self.assertAlmostEqual(
            field.get(
                4,
                2,
            ),
            1.0,
            places=6,
        )

    def test_single_pixel_exact_diagonal_distance(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_single_pixel_mask(),
                horizontal_extent=1.0,
                vertical_extent=1.0,
            )
        )

        self.assertAlmostEqual(
            field.get(
                4,
                4,
            ),
            math.sqrt(
                2.0
            ),
            places=6,
        )

    def test_square_center_is_deeper_than_boundary(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_square_mask()
            )
        )

        center = (
            field.get(
                3,
                3,
            )
        )

        boundary = (
            field.get(
                2,
                3,
            )
        )

        outside = (
            field.get(
                1,
                3,
            )
        )

        self.assertLess(
            center,
            boundary,
        )

        self.assertLess(
            boundary,
            0.0,
        )

        self.assertGreater(
            outside,
            0.0,
        )

    def test_circle_has_correct_sign(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                circle_mask_9()
            )
        )

        self.assertLess(
            field.get(
                4,
                4,
            ),
            0.0,
        )

        self.assertLess(
            field.get(
                4,
                1,
            ),
            0.0,
        )

        self.assertGreater(
            field.get(
                0,
                0,
            ),
            0.0,
        )

    def test_empty_mask_remains_finite_and_outside(
        self,
    ) -> None:
        mask = BinaryMask(
            width=5,
            height=5,
            values=bytes(
                25
            ),
        )

        field = (
            build_signed_distance_mask(
                mask
            )
        )

        self.assertTrue(
            field.empty
        )

        self.assertFalse(
            field.full
        )

        for value in (
            field.values
        ):
            self.assertTrue(
                math.isfinite(
                    value
                )
            )

            self.assertGreater(
                value,
                0.0,
            )

    def test_full_mask_remains_finite_and_inside(
        self,
    ) -> None:
        mask = BinaryMask(
            width=5,
            height=5,
            values=bytes(
                [
                    1
                ]
                * 25
            ),
        )

        field = (
            build_signed_distance_mask(
                mask
            )
        )

        self.assertTrue(
            field.full
        )

        self.assertFalse(
            field.empty
        )

        for value in (
            field.values
        ):
            self.assertTrue(
                math.isfinite(
                    value
                )
            )

            self.assertLess(
                value,
                0.0,
            )

    def test_bilinear_sampling_preserves_center_sign(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_square_mask()
            )
        )

        value = (
            field.sample_uv(
                0.5,
                0.5,
            )
        )

        self.assertLess(
            value,
            0.0,
        )

    def test_sampling_outside_image_is_positive(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_square_mask()
            )
        )

        self.assertGreater(
            field.sample_uv(
                -0.25,
                0.5,
            ),
            0.0,
        )

        self.assertGreater(
            field.sample_uv(
                1.25,
                0.5,
            ),
            0.0,
        )

    def test_invalid_extents_are_rejected(
        self,
    ) -> None:
        mask = (
            centered_square_mask()
        )

        for value in (
            0.0,
            -1.0,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    build_signed_distance_mask(
                        mask,
                        horizontal_extent=value,
                    )

    def test_wrong_mask_type_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            build_signed_distance_mask(
                object()
            )


# =========================================================
# SDFProjection
# =========================================================

class SDFProjectionTests(
    unittest.TestCase
):
    def test_front_projection_center_is_inside(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            )
        )

        value = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=0.0,
                    z=0.0,
                )
            )
        )

        self.assertLess(
            value,
            0.0,
        )

    def test_front_projection_ignores_depth_axis(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        first = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=-1.0,
                    z=0.0,
                )
            )
        )

        second = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=1.0,
                    z=0.0,
                )
            )
        )

        self.assertAlmostEqual(
            first,
            second,
            places=6,
        )

    def test_front_projection_outside_x_is_positive(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        value = (
            projection.sample(
                NormalizedPoint(
                    x=1.0,
                    y=0.0,
                    z=0.0,
                )
            )
        )

        self.assertGreater(
            value,
            0.0,
        )

    def test_right_projection_constrains_y_axis(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                name="Right",
            )
        )

        center = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=0.0,
                    z=0.0,
                )
            )
        )

        outside = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=1.0,
                    z=0.0,
                )
            )
        )

        self.assertLess(
            center,
            0.0,
        )

        self.assertGreater(
            outside,
            0.0,
        )

    def test_from_source_view_uses_capabilities(
        self,
    ) -> None:
        view = SimpleNamespace(
            name="Synthetic",
            mask=(
                centered_square_mask()
            ),
            azimuth_degrees=45.0,
            elevation_degrees=10.0,
            flip_x=True,
        )

        projection = (
            SDFProjection
            .from_source_view(
                view
            )
        )

        self.assertEqual(
            projection.name,
            "Synthetic",
        )

        self.assertAlmostEqual(
            projection
            .transform
            .azimuth_degrees,
            45.0,
        )

        self.assertAlmostEqual(
            projection
            .transform
            .elevation_degrees,
            10.0,
        )

        self.assertTrue(
            projection
            .transform
            .flip_x
        )

    def test_build_sdf_projections(
        self,
    ) -> None:
        views = (
            SimpleNamespace(
                name="Front",
                mask=(
                    centered_square_mask()
                ),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),
            SimpleNamespace(
                name="Right",
                mask=(
                    centered_square_mask()
                ),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),
        )

        projections = (
            build_sdf_projections(
                views
            )
        )

        self.assertEqual(
            len(
                projections
            ),
            2,
        )

        self.assertEqual(
            projections[0].name,
            "Front",
        )

        self.assertEqual(
            projections[1].name,
            "Right",
        )


# =========================================================
# CSG fusion
# =========================================================

class SDFFusionTests(
    unittest.TestCase
):
    def test_hard_fusion_is_maximum(
        self,
    ) -> None:
        self.assertEqual(
            fuse_signed_distances(
                (
                    -0.5,
                    -0.2,
                    -0.8,
                )
            ),
            -0.2,
        )

        self.assertEqual(
            fuse_signed_distances(
                (
                    -0.5,
                    0.3,
                    -0.2,
                )
            ),
            0.3,
        )

    def test_intersection_requires_all_views_inside(
        self,
    ) -> None:
        front = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            )
        )

        right = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                name="Right",
            )
        )

        projections = (
            front,
            right,
        )

        center = (
            sample_fused_sdf(
                NormalizedPoint(
                    x=0.0,
                    y=0.0,
                    z=0.0,
                ),
                projections,
            )
        )

        outside_front = (
            sample_fused_sdf(
                NormalizedPoint(
                    x=1.0,
                    y=0.0,
                    z=0.0,
                ),
                projections,
            )
        )

        outside_right = (
            sample_fused_sdf(
                NormalizedPoint(
                    x=0.0,
                    y=1.0,
                    z=0.0,
                ),
                projections,
            )
        )

        self.assertLess(
            center,
            0.0,
        )

        self.assertGreater(
            outside_front,
            0.0,
        )

        self.assertGreater(
            outside_right,
            0.0,
        )

    def test_smooth_max_equals_hard_max_outside_band(
        self,
    ) -> None:
        self.assertAlmostEqual(
            smooth_max(
                -2.0,
                1.0,
                0.5,
            ),
            1.0,
        )

    def test_smooth_max_rounds_equal_constraints(
        self,
    ) -> None:
        value = (
            smooth_max(
                0.0,
                0.0,
                1.0,
            )
        )

        self.assertAlmostEqual(
            value,
            0.25,
            places=6,
        )

    def test_smooth_max_is_commutative(
        self,
    ) -> None:
        a = (
            smooth_max(
                -0.2,
                0.1,
                0.5,
            )
        )

        b = (
            smooth_max(
                0.1,
                -0.2,
                0.5,
            )
        )

        self.assertAlmostEqual(
            a,
            b,
            places=8,
        )

    def test_negative_smoothness_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            smooth_max(
                0.0,
                0.0,
                -1.0,
            )

    def test_surface_offset_expands_field(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        point = NormalizedPoint(
            x=1.0,
            y=0.0,
            z=0.0,
        )

        base = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                surface_offset=0.0,
            )
        )

        expanded = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                surface_offset=0.25,
            )
        )

        self.assertAlmostEqual(
            expanded,
            base - 0.25,
            places=6,
        )


# =========================================================
# Conservative X symmetry
# =========================================================

class SDFSymmetryTests(
    unittest.TestCase
):
    def test_symmetry_requires_mirrored_point_to_survive(
        self,
    ) -> None:
        mask = mask_from_rows(
            ".....",
            ".....",
            "##...",
            "##...",
            ".....",
        )

        projection = (
            SDFProjection.from_mask(
                mask,
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        point = NormalizedPoint(
            x=-0.75,
            y=0.0,
            z=-0.25,
        )

        without_symmetry = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                symmetry_x=False,
            )
        )

        with_symmetry = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                symmetry_x=True,
            )
        )

        self.assertLess(
            without_symmetry,
            0.0,
        )

        self.assertGreater(
            with_symmetry,
            0.0,
        )


# =========================================================
# SDFBuildConfig
# =========================================================

class SDFBuildConfigTests(
    unittest.TestCase
):
    def test_default_constants(
        self,
    ) -> None:
        self.assertEqual(
            DEFAULT_ISO_LEVEL,
            0.0,
        )

        self.assertEqual(
            DEFAULT_SMOOTHNESS,
            0.0,
        )

        self.assertEqual(
            DEFAULT_SURFACE_OFFSET,
            0.0,
        )

        self.assertFalse(
            DEFAULT_SYMMETRY_X
        )

    def test_valid_config(
        self,
    ) -> None:
        config = SDFBuildConfig(
            width=8,
            depth=9,
            height=10,
        )

        config.validate()

        self.assertEqual(
            config.dimensions,
            (
                8,
                9,
                10,
            ),
        )

        self.assertEqual(
            config.voxel_count,
            720,
        )

    def test_cubic_config(
        self,
    ) -> None:
        config = (
            cubic_sdf_config(
                16
            )
        )

        self.assertEqual(
            config.dimensions,
            (
                16,
                16,
                16,
            ),
        )

        self.assertEqual(
            config.voxel_count,
            4096,
        )

    def test_dimension_below_two_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFBuildConfig(
                width=1,
                depth=8,
                height=8,
            ).validate()

    def test_negative_smoothness_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFBuildConfig(
                width=8,
                depth=8,
                height=8,
                smoothness=-0.1,
            ).validate()

    def test_reference_volume_limit_is_enforced(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFBuildConfig(
                width=10,
                depth=10,
                height=10,
                max_voxels=999,
            ).validate()


# =========================================================
# SDFVolume
# =========================================================

class SDFVolumeTests(
    unittest.TestCase
):
    def test_index_layout_x_is_fastest(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    0.0,
                    1.0,
                    2.0,
                    3.0,
                    4.0,
                    5.0,
                    6.0,
                    7.0,
                ),
            ),
        )

        self.assertEqual(
            volume.index(
                0,
                0,
                0,
            ),
            0,
        )

        self.assertEqual(
            volume.index(
                1,
                0,
                0,
            ),
            1,
        )

        self.assertEqual(
            volume.index(
                0,
                1,
                0,
            ),
            2,
        )

        self.assertEqual(
            volume.index(
                0,
                0,
                1,
            ),
            4,
        )

    def test_trilinear_center_is_average_of_corners(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    0.0,
                    1.0,
                    2.0,
                    3.0,
                    4.0,
                    5.0,
                    6.0,
                    7.0,
                ),
            ),
        )

        self.assertAlmostEqual(
            volume.sample_normalized(
                0.0,
                0.0,
                0.0,
            ),
            3.5,
            places=6,
        )

    def test_inside_uses_iso_level(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                ),
            ),
        )

        self.assertTrue(
            volume.inside(
                0,
                0,
                0,
            )
        )

        self.assertFalse(
            volume.inside(
                1,
                0,
                0,
            )
        )

    def test_cell_surface_crossing(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                ),
            ),
        )

        self.assertTrue(
            volume.cell_crosses_surface(
                0,
                0,
                0,
            )
        )

    def test_constant_inside_cell_does_not_cross_surface(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                ),
            ),
        )

        self.assertFalse(
            volume.cell_crosses_surface(
                0,
                0,
                0,
            )
        )

    def test_occupancy_conversion(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    1.0,
                    0.0,
                    2.0,
                    -2.0,
                    3.0,
                    -3.0,
                    4.0,
                ),
            ),
        )

        self.assertEqual(
            volume.to_occupancy_bytes(),
            bytes(
                (
                    1,
                    0,
                    1,
                    0,
                    1,
                    0,
                    1,
                    0,
                )
            ),
        )

    def test_wrong_value_count_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFVolume(
                width=2,
                depth=2,
                height=2,
                values=array(
                    "f",
                    (
                        0.0,
                    ),
                ),
            )


# =========================================================
# Dense 3D SDF build
# =========================================================

class SDFBuildTests(
    unittest.TestCase
):
    def test_build_single_projection_volume(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            )
        )

        config = (
            cubic_sdf_config(
                7
            )
        )

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=config,
            )
        )

        self.assertEqual(
            result.volume.dimensions,
            (
                7,
                7,
                7,
            ),
        )

        self.assertEqual(
            result.stats.voxel_count,
            343,
        )

        self.assertEqual(
            result.stats.projection_count,
            1,
        )

        self.assertEqual(
            result.stats
            .projection_sample_count,
            343,
        )

        self.assertTrue(
            result.volume
            .has_inside_samples
        )

        self.assertTrue(
            result.volume
            .has_outside_samples
        )

        self.assertTrue(
            result.volume
            .crosses_surface
        )

        self.assertLess(
            result.stats.minimum_distance,
            0.0,
        )

        self.assertGreater(
            result.stats.maximum_distance,
            0.0,
        )

    def test_two_projection_intersection_volume(
        self,
    ) -> None:
        projections = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            ),

            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                name="Right",
            ),
        )

        result = (
            build_sdf_volume(
                projections,
                config=(
                    cubic_sdf_config(
                        7
                    )
                ),
            )
        )

        center = (
            result.volume.get(
                3,
                3,
                3,
            )
        )

        x_edge = (
            result.volume.get(
                6,
                3,
                3,
            )
        )

        y_edge = (
            result.volume.get(
                3,
                6,
                3,
            )
        )

        self.assertLess(
            center,
            0.0,
        )

        self.assertGreater(
            x_edge,
            0.0,
        )

        self.assertGreater(
            y_edge,
            0.0,
        )

        self.assertEqual(
            result.stats
            .projection_sample_count,
            (
                7
                * 7
                * 7
                * 2
            ),
        )

    def test_symmetry_doubles_projection_sampling_stats(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=(
                    cubic_sdf_config(
                        5,
                        symmetry_x=True,
                    )
                ),
            )
        )

        self.assertEqual(
            result.stats
            .projection_sample_count,
            (
                5
                * 5
                * 5
                * 2
            ),
        )

    def test_progress_callback_runs_once_per_z_slice(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        progress = []

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=(
                    SDFBuildConfig(
                        width=5,
                        depth=6,
                        height=7,
                    )
                ),
                progress_callback=(
                    progress.append
                ),
            )
        )

        self.assertEqual(
            len(
                progress
            ),
            7,
        )

        self.assertEqual(
            progress[0]
            .completed_slices,
            1,
        )

        self.assertEqual(
            progress[-1]
            .completed_slices,
            7,
        )

        self.assertAlmostEqual(
            progress[-1]
            .fraction,
            1.0,
        )

        self.assertEqual(
            result.stats.voxel_count,
            (
                5
                * 6
                * 7
            ),
        )

    def test_build_from_source_views(
        self,
    ) -> None:
        views = (
            SimpleNamespace(
                name="Front",
                mask=(
                    centered_large_square_mask()
                ),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),

            SimpleNamespace(
                name="Right",
                mask=(
                    centered_large_square_mask()
                ),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),
        )

        result = (
            build_sdf_from_views(
                views,
                config=(
                    cubic_sdf_config(
                        5
                    )
                ),
            )
        )

        self.assertEqual(
            len(
                result.projections
            ),
            2,
        )

        self.assertEqual(
            result.stats
            .projection_count,
            2,
        )

        self.assertTrue(
            result.volume
            .crosses_surface
        )

    def test_sample_classification_counts_match_volume(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=(
                    cubic_sdf_config(
                        5
                    )
                ),
            )
        )

        classified = (
            result.stats.negative_samples
            + result.stats.zero_samples
            + result.stats.positive_samples
        )

        self.assertEqual(
            classified,
            result.stats.voxel_count,
        )


# =========================================================
# Visual-hull semantic regression
# =========================================================

class SDFVisualHullSemanticsTests(
    unittest.TestCase
):
    def test_hard_sdf_intersection_matches_boolean_logic(
        self,
    ) -> None:
        """
        With smoothness=0:

            fused <= 0

        must mean:

            every projection <= 0

        This is the continuous equivalent of the current
        Visual Hull silhouette intersection.
        """

        projections = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            ),

            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
            ),
        )

        points = (
            NormalizedPoint(
                x=0.0,
                y=0.0,
                z=0.0,
            ),

            NormalizedPoint(
                x=1.0,
                y=0.0,
                z=0.0,
            ),

            NormalizedPoint(
                x=0.0,
                y=1.0,
                z=0.0,
            ),

            NormalizedPoint(
                x=1.0,
                y=1.0,
                z=0.0,
            ),
        )

        for point in points:
            individual = [
                projection.sample(
                    point
                )
                for projection
                in projections
            ]

            fused = (
                sample_fused_sdf(
                    point,
                    projections,
                    smoothness=0.0,
                )
            )

            expected_inside = all(
                value <= 0.0
                for value
                in individual
            )

            actual_inside = (
                fused <= 0.0
            )

            self.assertEqual(
                actual_inside,
                expected_inside,
                msg=(
                    f"Point: {point}, "
                    f"individual={individual}, "
                    f"fused={fused}"
                ),
            )


# =========================================================
# Entry point
# =========================================================

if __name__ == "__main__":
    unittest.main()