# tests/test_visual_hull.py

from __future__ import annotations

import unittest

from core.masks import BinaryMask
from core.visual_hull import (
    ProjectionView,
    VisualHullOptions,
    build_visual_hull,
    crop_empty_bounds,
    enforce_volume_symmetry_x,
    find_occupied_bounds,
)


def mask_from_rows(
    rows: list[str],
) -> BinaryMask:
    if not rows:
        raise ValueError("Rows cannot be empty.")

    width = len(rows[0])
    height = len(rows)

    values: list[bool] = []

    for row in rows:
        if len(row) != width:
            raise ValueError(
                "All rows must have the same width."
            )

        for character in row:
            values.append(
                character == "#"
            )

    return BinaryMask(
        width=width,
        height=height,
        values=tuple(values),
    )


def full_mask(
    size: int = 8,
) -> BinaryMask:
    return mask_from_rows(
        [
            "#" * size
            for _ in range(size)
        ]
    )


def empty_mask(
    size: int = 8,
) -> BinaryMask:
    return mask_from_rows(
        [
            "." * size
            for _ in range(size)
        ]
    )


class VisualHullTests(unittest.TestCase):
    def test_requires_at_least_two_enabled_projections(
        self,
    ) -> None:
        projection = ProjectionView(
            mask=full_mask(),
            azimuth_degrees=0.0,
        )

        with self.assertRaises(ValueError):
            build_visual_hull(
                [projection],
                options=VisualHullOptions(
                    resolution=8,
                ),
            )

    def test_builds_volume_from_front_and_side(
        self,
    ) -> None:
        front = ProjectionView(
            mask=mask_from_rows(
                [
                    "........",
                    "........",
                    "..####..",
                    "..####..",
                    "..####..",
                    "..####..",
                    "........",
                    "........",
                ]
            ),
            azimuth_degrees=0.0,
        )

        side = ProjectionView(
            mask=mask_from_rows(
                [
                    "........",
                    "........",
                    "...##...",
                    "..####..",
                    "..####..",
                    "...##...",
                    "........",
                    "........",
                ]
            ),
            azimuth_degrees=90.0,
        )

        volume = build_visual_hull(
            [
                front,
                side,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        self.assertGreater(
            volume.occupied_count,
            0,
        )

        self.assertEqual(
            volume.width,
            8,
        )

        self.assertEqual(
            volume.depth,
            8,
        )

        self.assertEqual(
            volume.height,
            8,
        )

    def test_empty_projection_produces_empty_volume(
        self,
    ) -> None:
        front = ProjectionView(
            mask=empty_mask(),
            azimuth_degrees=0.0,
        )

        side = ProjectionView(
            mask=full_mask(),
            azimuth_degrees=90.0,
        )

        volume = build_visual_hull(
            [
                front,
                side,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        self.assertEqual(
            volume.occupied_count,
            0,
        )

    def test_additional_projection_restricts_volume(
        self,
    ) -> None:
        front = ProjectionView(
            mask=full_mask(),
            azimuth_degrees=0.0,
        )

        side = ProjectionView(
            mask=full_mask(),
            azimuth_degrees=90.0,
        )

        diagonal = ProjectionView(
            mask=mask_from_rows(
                [
                    "........",
                    "..####..",
                    ".######.",
                    ".######.",
                    ".######.",
                    ".######.",
                    "..####..",
                    "........",
                ]
            ),
            azimuth_degrees=45.0,
        )

        without_diagonal = build_visual_hull(
            [
                front,
                side,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        with_diagonal = build_visual_hull(
            [
                front,
                side,
                diagonal,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        self.assertLess(
            with_diagonal.occupied_count,
            without_diagonal.occupied_count,
        )

    def test_disabled_projection_is_ignored(
        self,
    ) -> None:
        front = ProjectionView(
            mask=full_mask(),
            azimuth_degrees=0.0,
        )

        side = ProjectionView(
            mask=full_mask(),
            azimuth_degrees=90.0,
        )

        disabled_empty = ProjectionView(
            mask=empty_mask(),
            azimuth_degrees=45.0,
            enabled=False,
        )

        volume = build_visual_hull(
            [
                front,
                side,
                disabled_empty,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        self.assertGreater(
            volume.occupied_count,
            0,
        )

    def test_eight_turntable_views_can_be_used(
        self,
    ) -> None:
        projections = [
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=index * 45.0,
            )
            for index in range(8)
        ]

        volume = build_visual_hull(
            projections,
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        self.assertGreater(
            volume.occupied_count,
            0,
        )

    def test_elevated_projection_can_be_used(
        self,
    ) -> None:
        projections = [
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            ),
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
            ),
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=45.0,
                elevation_degrees=30.0,
            ),
        ]

        volume = build_visual_hull(
            projections,
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        self.assertGreater(
            volume.occupied_count,
            0,
        )

    def test_flip_x_can_be_used(
        self,
    ) -> None:
        asymmetric_mask = mask_from_rows(
            [
                "........",
                "........",
                ".###....",
                ".###....",
                ".###....",
                ".###....",
                "........",
                "........",
            ]
        )

        front = ProjectionView(
            mask=asymmetric_mask,
            azimuth_degrees=0.0,
        )

        side = ProjectionView(
            mask=full_mask(),
            azimuth_degrees=90.0,
        )

        flipped_front = ProjectionView(
            mask=asymmetric_mask,
            azimuth_degrees=0.0,
            flip_x=True,
        )

        normal_volume = build_visual_hull(
            [
                front,
                side,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        flipped_volume = build_visual_hull(
            [
                flipped_front,
                side,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        self.assertEqual(
            normal_volume.occupied_count,
            flipped_volume.occupied_count,
        )

    def test_find_occupied_bounds(
        self,
    ) -> None:
        front = ProjectionView(
            mask=mask_from_rows(
                [
                    "........",
                    "........",
                    "...##...",
                    "...##...",
                    "...##...",
                    "...##...",
                    "........",
                    "........",
                ]
            ),
            azimuth_degrees=0.0,
        )

        side = ProjectionView(
            mask=mask_from_rows(
                [
                    "........",
                    "........",
                    "...##...",
                    "...##...",
                    "...##...",
                    "...##...",
                    "........",
                    "........",
                ]
            ),
            azimuth_degrees=90.0,
        )

        volume = build_visual_hull(
            [
                front,
                side,
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        bounds = find_occupied_bounds(
            volume
        )

        self.assertIsNotNone(
            bounds
        )

        assert bounds is not None

        (
            min_x,
            max_x,
            min_y,
            max_y,
            min_z,
            max_z,
        ) = bounds

        self.assertLessEqual(
            min_x,
            max_x,
        )

        self.assertLessEqual(
            min_y,
            max_y,
        )

        self.assertLessEqual(
            min_z,
            max_z,
        )

    def test_crop_empty_bounds_reduces_dimensions(
        self,
    ) -> None:
        shape = mask_from_rows(
            [
                "........",
                "........",
                "...##...",
                "...##...",
                "...##...",
                "...##...",
                "........",
                "........",
            ]
        )

        volume = build_visual_hull(
            [
                ProjectionView(
                    mask=shape,
                    azimuth_degrees=0.0,
                ),
                ProjectionView(
                    mask=shape,
                    azimuth_degrees=90.0,
                ),
            ],
            options=VisualHullOptions(
                resolution=8,
            ),
        )

        cropped = crop_empty_bounds(
            volume
        )

        self.assertLess(
            cropped.width,
            volume.width,
        )

        self.assertLess(
            cropped.depth,
            volume.depth,
        )

        self.assertLess(
            cropped.height,
            volume.height,
        )

    def test_symmetry_preserves_or_adds_voxels(
        self,
    ) -> None:
        asymmetric = mask_from_rows(
            [
                "........",
                "........",
                ".###....",
                ".###....",
                ".###....",
                ".###....",
                "........",
                "........",
            ]
        )

        volume = build_visual_hull(
            [
                ProjectionView(
                    mask=asymmetric,
                    azimuth_degrees=0.0,
                ),
                ProjectionView(
                    mask=full_mask(),
                    azimuth_degrees=90.0,
                ),
            ],
            options=VisualHullOptions(
                resolution=8,
                symmetry_x=False,
            ),
        )

        symmetric = enforce_volume_symmetry_x(
            volume
        )

        self.assertGreaterEqual(
            symmetric.occupied_count,
            volume.occupied_count,
        )

    def test_invalid_low_resolution_raises(
        self,
    ) -> None:
        projections = [
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=0.0,
            ),
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=90.0,
            ),
        ]

        with self.assertRaises(ValueError):
            build_visual_hull(
                projections,
                options=VisualHullOptions(
                    resolution=4,
                ),
            )

    def test_invalid_high_resolution_raises(
        self,
    ) -> None:
        projections = [
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=0.0,
            ),
            ProjectionView(
                mask=full_mask(),
                azimuth_degrees=90.0,
            ),
        ]

        with self.assertRaises(ValueError):
            build_visual_hull(
                projections,
                options=VisualHullOptions(
                    resolution=512,
                ),
            )


if __name__ == "__main__":
    unittest.main()