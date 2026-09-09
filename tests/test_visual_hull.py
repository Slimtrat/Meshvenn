from __future__ import annotations

import unittest

from core.masks import BinaryMask
from core.visual_hull import (
    ProjectionView,
    VisualHullOptions,
    VisualHullSession,
    build_visual_hull,
    crop_empty_bounds,
    enforce_volume_symmetry_x,
    find_occupied_bounds,
)


def mask_from_rows(rows: list[str]) -> BinaryMask:
    if not rows:
        raise ValueError("Rows cannot be empty.")

    width = len(rows[0])
    values = bytearray()

    for row in rows:
        if len(row) != width:
            raise ValueError("All rows must have the same width.")
        values.extend(1 if char == "#" else 0 for char in row)

    return BinaryMask(
        width=width,
        height=len(rows),
        values=bytes(values),
    )


def full_mask(size: int = 8) -> BinaryMask:
    return mask_from_rows(["#" * size for _ in range(size)])


def empty_mask(size: int = 8) -> BinaryMask:
    return mask_from_rows(["." * size for _ in range(size)])


class VisualHullTests(unittest.TestCase):
    def test_requires_at_least_two_enabled_projections(self) -> None:
        with self.assertRaises(ValueError):
            build_visual_hull(
                [ProjectionView(mask=full_mask())],
                options=VisualHullOptions(resolution=8),
            )

    def test_builds_volume_from_front_and_side(self) -> None:
        shape = mask_from_rows(
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
        )

        volume = build_visual_hull(
            [
                ProjectionView(mask=shape, azimuth_degrees=0.0),
                ProjectionView(mask=shape, azimuth_degrees=90.0),
            ],
            options=VisualHullOptions(resolution=8),
        )

        self.assertGreater(volume.occupied_count, 0)
        self.assertEqual((volume.width, volume.depth, volume.height), (8, 8, 8))

    def test_empty_projection_produces_empty_volume(self) -> None:
        volume = build_visual_hull(
            [
                ProjectionView(mask=empty_mask(), azimuth_degrees=0.0),
                ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
            ],
            options=VisualHullOptions(resolution=8),
        )
        self.assertEqual(volume.occupied_count, 0)

    def test_additional_projection_restricts_volume(self) -> None:
        diagonal = mask_from_rows(
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
        )

        first_two = [
            ProjectionView(mask=full_mask(), azimuth_degrees=0.0),
            ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
        ]

        without = build_visual_hull(
            first_two,
            options=VisualHullOptions(resolution=8),
        )
        with_diagonal = build_visual_hull(
            first_two + [ProjectionView(mask=diagonal, azimuth_degrees=45.0)],
            options=VisualHullOptions(resolution=8),
        )

        self.assertLess(with_diagonal.occupied_count, without.occupied_count)

    def test_incremental_session_matches_regular_build(self) -> None:
        projections = [
            ProjectionView(mask=full_mask(), azimuth_degrees=0.0),
            ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
            ProjectionView(
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
            ),
        ]

        regular = build_visual_hull(
            projections,
            options=VisualHullOptions(resolution=8),
        )

        session = VisualHullSession(
            options=VisualHullOptions(resolution=8)
        )
        for projection in projections:
            session.apply_view(projection)

        incremental = session.snapshot()

        self.assertEqual(regular.values, incremental.values)
        self.assertEqual(
            regular.occupied_count,
            incremental.occupied_count,
        )

    def test_incremental_snapshot_can_be_reused_for_levels(self) -> None:
        session = VisualHullSession(
            options=VisualHullOptions(resolution=8)
        )

        session.apply_view(
            ProjectionView(mask=full_mask(), azimuth_degrees=0.0)
        )
        session.apply_view(
            ProjectionView(mask=full_mask(), azimuth_degrees=90.0)
        )
        l2 = session.snapshot()

        session.apply_view(
            ProjectionView(
                mask=mask_from_rows(
                    [
                        "........",
                        "..####..",
                        "..####..",
                        "..####..",
                        "..####..",
                        "..####..",
                        "..####..",
                        "........",
                    ]
                ),
                azimuth_degrees=180.0,
            )
        )
        l3 = session.snapshot()

        self.assertLessEqual(l3.occupied_count, l2.occupied_count)
        self.assertGreater(l2.occupied_count, 0)

    def test_disabled_projection_is_ignored(self) -> None:
        volume = build_visual_hull(
            [
                ProjectionView(mask=full_mask(), azimuth_degrees=0.0),
                ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
                ProjectionView(
                    mask=empty_mask(),
                    azimuth_degrees=45.0,
                    enabled=False,
                ),
            ],
            options=VisualHullOptions(resolution=8),
        )
        self.assertGreater(volume.occupied_count, 0)

    def test_eight_turntable_views_can_be_used(self) -> None:
        volume = build_visual_hull(
            [
                ProjectionView(
                    mask=full_mask(),
                    azimuth_degrees=index * 45.0,
                )
                for index in range(8)
            ],
            options=VisualHullOptions(resolution=8),
        )
        self.assertGreater(volume.occupied_count, 0)

    def test_elevated_projection_can_be_used(self) -> None:
        volume = build_visual_hull(
            [
                ProjectionView(mask=full_mask(), azimuth_degrees=0.0),
                ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
                ProjectionView(
                    mask=full_mask(),
                    azimuth_degrees=45.0,
                    elevation_degrees=30.0,
                ),
            ],
            options=VisualHullOptions(resolution=8),
        )
        self.assertGreater(volume.occupied_count, 0)

    def test_flip_x_preserves_count(self) -> None:
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

        normal = build_visual_hull(
            [
                ProjectionView(mask=asymmetric, azimuth_degrees=0.0),
                ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
            ],
            options=VisualHullOptions(resolution=8),
        )

        flipped = build_visual_hull(
            [
                ProjectionView(
                    mask=asymmetric,
                    azimuth_degrees=0.0,
                    flip_x=True,
                ),
                ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
            ],
            options=VisualHullOptions(resolution=8),
        )

        self.assertEqual(normal.occupied_count, flipped.occupied_count)

    def test_bounds_are_available_without_rescan_semantics_change(self) -> None:
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
                ProjectionView(mask=shape, azimuth_degrees=0.0),
                ProjectionView(mask=shape, azimuth_degrees=90.0),
            ],
            options=VisualHullOptions(resolution=8),
        )

        bounds = find_occupied_bounds(volume)
        self.assertIsNotNone(bounds)

    def test_crop_empty_bounds_reduces_dimensions(self) -> None:
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
                ProjectionView(mask=shape, azimuth_degrees=0.0),
                ProjectionView(mask=shape, azimuth_degrees=90.0),
            ],
            options=VisualHullOptions(resolution=8),
        )

        cropped = crop_empty_bounds(volume)
        self.assertLess(cropped.width, volume.width)
        self.assertLess(cropped.depth, volume.depth)
        self.assertLess(cropped.height, volume.height)
        self.assertEqual(cropped.occupied_count, volume.occupied_count)

    def test_symmetry_preserves_or_adds_voxels(self) -> None:
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
                ProjectionView(mask=asymmetric, azimuth_degrees=0.0),
                ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
            ],
            options=VisualHullOptions(resolution=8),
        )

        symmetric = enforce_volume_symmetry_x(volume)
        self.assertGreaterEqual(
            symmetric.occupied_count,
            volume.occupied_count,
        )

    def test_invalid_resolution_raises(self) -> None:
        projections = [
            ProjectionView(mask=full_mask(), azimuth_degrees=0.0),
            ProjectionView(mask=full_mask(), azimuth_degrees=90.0),
        ]

        with self.assertRaises(ValueError):
            build_visual_hull(
                projections,
                options=VisualHullOptions(resolution=4),
            )

        with self.assertRaises(ValueError):
            build_visual_hull(
                projections,
                options=VisualHullOptions(resolution=512),
            )


if __name__ == "__main__":
    unittest.main()
