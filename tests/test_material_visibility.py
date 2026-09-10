from __future__ import annotations

import math
import sys
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import (
    MagicMock,
    patch,
)


# ---------------------------------------------------------
# Repository import
# ---------------------------------------------------------

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.material_visibility import (
    DEFAULT_ABSOLUTE_EPSILON,
    DEFAULT_RAY_LENGTH_MULTIPLIER,
    DEFAULT_RELATIVE_EPSILON,
    MeshVisibilityTester,
    RaycastHit,
    VisibilityConfig,
    bounding_box_diagonal,
    compute_ray_distance,
    compute_surface_epsilon,
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

class RecordingRaycast:
    """
    Small deterministic raycast fake.

    Tests can configure one result and inspect the exact ray
    submitted by MeshVisibilityTester.
    """

    def __init__(
        self,
        result: RaycastHit | None = None,
    ) -> None:
        self.result = result

        self.calls: list[
            tuple[
                tuple[
                    float,
                    float,
                    float,
                ],
                tuple[
                    float,
                    float,
                    float,
                ],
                float,
            ]
        ] = []

    def __call__(
        self,
        origin: tuple[
            float,
            float,
            float,
        ],
        direction: tuple[
            float,
            float,
            float,
        ],
        distance: float,
    ) -> RaycastHit | None:
        self.calls.append(
            (
                origin,
                direction,
                distance,
            )
        )

        return self.result


def assert_vector_almost_equal(
    testcase: unittest.TestCase,
    actual: tuple[
        float,
        float,
        float,
    ],
    expected: tuple[
        float,
        float,
        float,
    ],
    *,
    places: int = 7,
) -> None:
    testcase.assertEqual(
        len(actual),
        3,
    )

    testcase.assertEqual(
        len(expected),
        3,
    )

    for (
        actual_component,
        expected_component,
    ) in zip(
        actual,
        expected,
    ):
        testcase.assertAlmostEqual(
            actual_component,
            expected_component,
            places=places,
        )


# ---------------------------------------------------------
# VisibilityConfig
# ---------------------------------------------------------

class VisibilityConfigTests(
    unittest.TestCase
):
    def test_default_configuration_is_valid(
        self,
    ) -> None:
        config = (
            VisibilityConfig()
        )

        config.validate()

        self.assertEqual(
            config.relative_epsilon,
            DEFAULT_RELATIVE_EPSILON,
        )

        self.assertEqual(
            config.absolute_epsilon,
            DEFAULT_ABSOLUTE_EPSILON,
        )

        self.assertEqual(
            config.ray_length_multiplier,
            DEFAULT_RAY_LENGTH_MULTIPLIER,
        )

    def test_zero_relative_epsilon_is_allowed(
        self,
    ) -> None:
        config = VisibilityConfig(
            relative_epsilon=0.0,
            absolute_epsilon=1e-6,
            ray_length_multiplier=2.0,
        )

        config.validate()

    def test_negative_relative_epsilon_is_rejected(
        self,
    ) -> None:
        config = VisibilityConfig(
            relative_epsilon=-1e-5,
        )

        with self.assertRaises(
            ValueError
        ):
            config.validate()

    def test_zero_absolute_epsilon_is_rejected(
        self,
    ) -> None:
        config = VisibilityConfig(
            absolute_epsilon=0.0,
        )

        with self.assertRaises(
            ValueError
        ):
            config.validate()

    def test_negative_absolute_epsilon_is_rejected(
        self,
    ) -> None:
        config = VisibilityConfig(
            absolute_epsilon=-1e-6,
        )

        with self.assertRaises(
            ValueError
        ):
            config.validate()

    def test_ray_multiplier_must_be_greater_than_one(
        self,
    ) -> None:
        for multiplier in (
            -1.0,
            0.0,
            0.5,
            1.0,
        ):
            with self.subTest(
                multiplier=multiplier
            ):
                config = (
                    VisibilityConfig(
                        ray_length_multiplier=(
                            multiplier
                        )
                    )
                )

                with self.assertRaises(
                    ValueError
                ):
                    config.validate()

    def test_non_finite_values_are_rejected(
        self,
    ) -> None:
        configs = [
            VisibilityConfig(
                relative_epsilon=(
                    math.inf
                )
            ),
            VisibilityConfig(
                relative_epsilon=(
                    math.nan
                )
            ),
            VisibilityConfig(
                absolute_epsilon=(
                    math.inf
                )
            ),
            VisibilityConfig(
                absolute_epsilon=(
                    math.nan
                )
            ),
            VisibilityConfig(
                ray_length_multiplier=(
                    math.inf
                )
            ),
            VisibilityConfig(
                ray_length_multiplier=(
                    math.nan
                )
            ),
        ]

        for config in configs:
            with self.subTest(
                config=config
            ):
                with self.assertRaises(
                    ValueError
                ):
                    config.validate()


# ---------------------------------------------------------
# Bounding box
# ---------------------------------------------------------

class BoundingBoxTests(
    unittest.TestCase
):
    def test_diagonal_for_known_box(
        self,
    ) -> None:
        diagonal = (
            bounding_box_diagonal(
                [
                    (
                        0.0,
                        0.0,
                        0.0,
                    ),
                    (
                        3.0,
                        4.0,
                        12.0,
                    ),
                ]
            )
        )

        self.assertAlmostEqual(
            diagonal,
            13.0,
        )

    def test_diagonal_supports_negative_coordinates(
        self,
    ) -> None:
        diagonal = (
            bounding_box_diagonal(
                [
                    (
                        -1.0,
                        -2.0,
                        -3.0,
                    ),
                    (
                        1.0,
                        2.0,
                        3.0,
                    ),
                ]
            )
        )

        expected = math.sqrt(
            (
                2.0
                ** 2
            )
            + (
                4.0
                ** 2
            )
            + (
                6.0
                ** 2
            )
        )

        self.assertAlmostEqual(
            diagonal,
            expected,
        )

    def test_diagonal_uses_all_vertices(
        self,
    ) -> None:
        diagonal = (
            bounding_box_diagonal(
                [
                    (
                        0.0,
                        0.0,
                        0.0,
                    ),
                    (
                        1.0,
                        50.0,
                        1.0,
                    ),
                    (
                        10.0,
                        1.0,
                        20.0,
                    ),
                    (
                        -5.0,
                        -10.0,
                        -2.0,
                    ),
                ]
            )
        )

        expected = math.sqrt(
            (
                15.0
                ** 2
            )
            + (
                60.0
                ** 2
            )
            + (
                22.0
                ** 2
            )
        )

        self.assertAlmostEqual(
            diagonal,
            expected,
        )

    def test_single_vertex_has_zero_diagonal(
        self,
    ) -> None:
        diagonal = (
            bounding_box_diagonal(
                [
                    (
                        5.0,
                        -3.0,
                        8.0,
                    )
                ]
            )
        )

        self.assertEqual(
            diagonal,
            0.0,
        )

    def test_empty_vertices_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            bounding_box_diagonal(
                []
            )

    def test_non_finite_vertex_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            bounding_box_diagonal(
                [
                    (
                        0.0,
                        math.inf,
                        0.0,
                    )
                ]
            )


# ---------------------------------------------------------
# Effective distances
# ---------------------------------------------------------

class VisibilityDistanceTests(
    unittest.TestCase
):
    def test_relative_epsilon_scales_with_mesh(
        self,
    ) -> None:
        config = VisibilityConfig(
            relative_epsilon=0.01,
            absolute_epsilon=0.001,
        )

        result = (
            compute_surface_epsilon(
                10.0,
                config,
            )
        )

        self.assertAlmostEqual(
            result,
            0.1,
        )

    def test_absolute_epsilon_is_minimum(
        self,
    ) -> None:
        config = VisibilityConfig(
            relative_epsilon=1e-6,
            absolute_epsilon=0.01,
        )

        result = (
            compute_surface_epsilon(
                10.0,
                config,
            )
        )

        self.assertEqual(
            result,
            0.01,
        )

    def test_zero_size_mesh_uses_absolute_epsilon(
        self,
    ) -> None:
        config = VisibilityConfig(
            relative_epsilon=0.01,
            absolute_epsilon=0.002,
        )

        result = (
            compute_surface_epsilon(
                0.0,
                config,
            )
        )

        self.assertEqual(
            result,
            0.002,
        )

    def test_ray_distance_uses_mesh_diagonal(
        self,
    ) -> None:
        config = VisibilityConfig(
            ray_length_multiplier=3.0,
        )

        result = (
            compute_ray_distance(
                mesh_diagonal=4.0,
                surface_epsilon=0.001,
                config=config,
            )
        )

        self.assertAlmostEqual(
            result,
            12.0,
        )

    def test_ray_distance_stays_valid_for_tiny_mesh(
        self,
    ) -> None:
        config = VisibilityConfig(
            ray_length_multiplier=2.0,
        )

        result = (
            compute_ray_distance(
                mesh_diagonal=0.0,
                surface_epsilon=0.01,
                config=config,
            )
        )

        self.assertGreaterEqual(
            result,
            0.1,
        )

    def test_negative_mesh_diagonal_is_rejected(
        self,
    ) -> None:
        config = (
            VisibilityConfig()
        )

        with self.assertRaises(
            ValueError
        ):
            compute_surface_epsilon(
                -1.0,
                config,
            )

        with self.assertRaises(
            ValueError
        ):
            compute_ray_distance(
                mesh_diagonal=-1.0,
                surface_epsilon=0.01,
                config=config,
            )

    def test_invalid_surface_epsilon_is_rejected(
        self,
    ) -> None:
        config = (
            VisibilityConfig()
        )

        for epsilon in (
            -1.0,
            0.0,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                epsilon=epsilon
            ):
                with self.assertRaises(
                    ValueError
                ):
                    compute_ray_distance(
                        mesh_diagonal=1.0,
                        surface_epsilon=epsilon,
                        config=config,
                    )


# ---------------------------------------------------------
# Visibility tester construction
# ---------------------------------------------------------

class VisibilityTesterConstructionTests(
    unittest.TestCase
):
    def test_raycast_must_be_callable(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            MeshVisibilityTester(
                None,  # type: ignore[arg-type]
                surface_epsilon=0.01,
                max_distance=10.0,
            )

    def test_surface_epsilon_must_be_positive(
        self,
    ) -> None:
        for epsilon in (
            -1.0,
            0.0,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                epsilon=epsilon
            ):
                with self.assertRaises(
                    ValueError
                ):
                    MeshVisibilityTester(
                        RecordingRaycast(),
                        surface_epsilon=(
                            epsilon
                        ),
                        max_distance=10.0,
                    )

    def test_max_distance_must_exceed_epsilon(
        self,
    ) -> None:
        for distance in (
            -1.0,
            0.0,
            0.005,
            0.01,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                distance=distance
            ):
                with self.assertRaises(
                    ValueError
                ):
                    MeshVisibilityTester(
                        RecordingRaycast(),
                        surface_epsilon=0.01,
                        max_distance=(
                            distance
                        ),
                    )


# ---------------------------------------------------------
# Clear visibility
# ---------------------------------------------------------

class ClearVisibilityTests(
    unittest.TestCase
):
    def test_no_hit_means_visible(
        self,
    ) -> None:
        raycast = (
            RecordingRaycast(
                None
            )
        )

        tester = (
            MeshVisibilityTester(
                raycast,
                surface_epsilon=0.01,
                max_distance=10.0,
            )
        )

        result = tester.query(
            (
                1.0,
                2.0,
                3.0,
            ),
            (
                0.0,
                -1.0,
                0.0,
            ),
        )

        self.assertTrue(
            result.visible
        )

        self.assertFalse(
            result.occluded
        )

        self.assertIsNone(
            result.hit_distance
        )

        self.assertIsNone(
            result.polygon_index
        )

    def test_ray_starts_offset_toward_camera(
        self,
    ) -> None:
        raycast = (
            RecordingRaycast()
        )

        tester = (
            MeshVisibilityTester(
                raycast,
                surface_epsilon=0.25,
                max_distance=10.0,
            )
        )

        tester.query(
            (
                1.0,
                2.0,
                3.0,
            ),
            (
                0.0,
                -1.0,
                0.0,
            ),
        )

        self.assertEqual(
            len(
                raycast.calls
            ),
            1,
        )

        (
            origin,
            direction,
            distance,
        ) = raycast.calls[0]

        assert_vector_almost_equal(
            self,
            origin,
            (
                1.0,
                1.75,
                3.0,
            ),
        )

        assert_vector_almost_equal(
            self,
            direction,
            (
                0.0,
                -1.0,
                0.0,
            ),
        )

        self.assertAlmostEqual(
            distance,
            9.75,
        )

    def test_camera_direction_is_normalized(
        self,
    ) -> None:
        raycast = (
            RecordingRaycast()
        )

        tester = (
            MeshVisibilityTester(
                raycast,
                surface_epsilon=0.1,
                max_distance=5.0,
            )
        )

        tester.query(
            (
                0.0,
                0.0,
                0.0,
            ),
            (
                0.0,
                -10.0,
                0.0,
            ),
        )

        (
            origin,
            direction,
            _,
        ) = raycast.calls[0]

        assert_vector_almost_equal(
            self,
            direction,
            (
                0.0,
                -1.0,
                0.0,
            ),
        )

        assert_vector_almost_equal(
            self,
            origin,
            (
                0.0,
                -0.1,
                0.0,
            ),
        )

    def test_is_visible_shortcut_returns_true(
        self,
    ) -> None:
        tester = (
            MeshVisibilityTester(
                RecordingRaycast(),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

        self.assertTrue(
            tester.is_visible(
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    1.0,
                    0.0,
                    0.0,
                ),
            )
        )


# ---------------------------------------------------------
# Occlusion
# ---------------------------------------------------------

class OcclusionTests(
    unittest.TestCase
):
    def test_hit_between_surface_and_camera_blocks_view(
        self,
    ) -> None:
        hit = RaycastHit(
            distance=2.0,
            polygon_index=42,
            position=(
                0.0,
                -2.01,
                0.0,
            ),
            normal=(
                0.0,
                1.0,
                0.0,
            ),
        )

        raycast = (
            RecordingRaycast(
                hit
            )
        )

        tester = (
            MeshVisibilityTester(
                raycast,
                surface_epsilon=0.01,
                max_distance=10.0,
            )
        )

        result = tester.query(
            (
                0.0,
                0.0,
                0.0,
            ),
            (
                0.0,
                -1.0,
                0.0,
            ),
        )

        self.assertFalse(
            result.visible
        )

        self.assertTrue(
            result.occluded
        )

        self.assertEqual(
            result.hit_distance,
            2.0,
        )

        self.assertEqual(
            result.polygon_index,
            42,
        )

    def test_is_visible_shortcut_returns_false(
        self,
    ) -> None:
        tester = (
            MeshVisibilityTester(
                RecordingRaycast(
                    RaycastHit(
                        distance=1.0
                    )
                ),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

        self.assertFalse(
            tester.is_visible(
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    1.0,
                    0.0,
                    0.0,
                ),
            )
        )


# ---------------------------------------------------------
# Self-intersection protection
# ---------------------------------------------------------

class SelfIntersectionTests(
    unittest.TestCase
):
    def test_zero_distance_hit_is_ignored(
        self,
    ) -> None:
        tester = (
            MeshVisibilityTester(
                RecordingRaycast(
                    RaycastHit(
                        distance=0.0,
                        polygon_index=3,
                    )
                ),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

        result = tester.query(
            (
                0.0,
                0.0,
                0.0,
            ),
            (
                1.0,
                0.0,
                0.0,
            ),
        )

        self.assertTrue(
            result.visible
        )

        self.assertFalse(
            result.occluded
        )

    def test_hit_inside_epsilon_is_ignored(
        self,
    ) -> None:
        tester = (
            MeshVisibilityTester(
                RecordingRaycast(
                    RaycastHit(
                        distance=0.005
                    )
                ),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

        result = tester.query(
            (
                0.0,
                0.0,
                0.0,
            ),
            (
                1.0,
                0.0,
                0.0,
            ),
        )

        self.assertTrue(
            result.visible
        )

    def test_hit_exactly_at_epsilon_is_ignored(
        self,
    ) -> None:
        tester = (
            MeshVisibilityTester(
                RecordingRaycast(
                    RaycastHit(
                        distance=0.01
                    )
                ),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

        result = tester.query(
            (
                0.0,
                0.0,
                0.0,
            ),
            (
                1.0,
                0.0,
                0.0,
            ),
        )

        self.assertTrue(
            result.visible
        )

    def test_hit_just_after_epsilon_blocks(
        self,
    ) -> None:
        tester = (
            MeshVisibilityTester(
                RecordingRaycast(
                    RaycastHit(
                        distance=0.0101
                    )
                ),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

        result = tester.query(
            (
                0.0,
                0.0,
                0.0,
            ),
            (
                1.0,
                0.0,
                0.0,
            ),
        )

        self.assertFalse(
            result.visible
        )

        self.assertTrue(
            result.occluded
        )


# ---------------------------------------------------------
# Defensive backend behaviour
# ---------------------------------------------------------

class RaycastBackendTests(
    unittest.TestCase
):
    def test_hit_beyond_requested_distance_is_ignored(
        self,
    ) -> None:
        raycast = (
            RecordingRaycast(
                RaycastHit(
                    distance=100.0
                )
            )
        )

        tester = (
            MeshVisibilityTester(
                raycast,
                surface_epsilon=0.1,
                max_distance=5.0,
            )
        )

        result = tester.query(
            (
                0.0,
                0.0,
                0.0,
            ),
            (
                1.0,
                0.0,
                0.0,
            ),
        )

        self.assertTrue(
            result.visible
        )

    def test_negative_hit_distance_is_rejected(
        self,
    ) -> None:
        tester = (
            MeshVisibilityTester(
                RecordingRaycast(
                    RaycastHit(
                        distance=-1.0
                    )
                ),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

        with self.assertRaises(
            ValueError
        ):
            tester.query(
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    1.0,
                    0.0,
                    0.0,
                ),
            )

    def test_non_finite_hit_distance_is_rejected(
        self,
    ) -> None:
        for distance in (
            math.inf,
            math.nan,
        ):
            with self.subTest(
                distance=distance
            ):
                tester = (
                    MeshVisibilityTester(
                        RecordingRaycast(
                            RaycastHit(
                                distance=(
                                    distance
                                )
                            )
                        ),
                        surface_epsilon=0.01,
                        max_distance=5.0,
                    )
                )

                with self.assertRaises(
                    ValueError
                ):
                    tester.query(
                        (
                            0.0,
                            0.0,
                            0.0,
                        ),
                        (
                            1.0,
                            0.0,
                            0.0,
                        ),
                    )


# ---------------------------------------------------------
# Invalid query data
# ---------------------------------------------------------

class VisibilityQueryValidationTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.tester = (
            MeshVisibilityTester(
                RecordingRaycast(),
                surface_epsilon=0.01,
                max_distance=5.0,
            )
        )

    def test_zero_camera_direction_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            self.tester.query(
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    0.0,
                    0.0,
                    0.0,
                ),
            )

    def test_non_finite_camera_direction_is_rejected(
        self,
    ) -> None:
        directions = [
            (
                math.inf,
                0.0,
                0.0,
            ),
            (
                math.nan,
                1.0,
                0.0,
            ),
        ]

        for direction in directions:
            with self.subTest(
                direction=direction
            ):
                with self.assertRaises(
                    ValueError
                ):
                    self.tester.query(
                        (
                            0.0,
                            0.0,
                            0.0,
                        ),
                        direction,
                    )

    def test_non_finite_position_is_rejected(
        self,
    ) -> None:
        positions = [
            (
                math.inf,
                0.0,
                0.0,
            ),
            (
                0.0,
                math.nan,
                0.0,
            ),
        ]

        for position in positions:
            with self.subTest(
                position=position
            ):
                with self.assertRaises(
                    ValueError
                ):
                    self.tester.query(
                        position,
                        (
                            1.0,
                            0.0,
                            0.0,
                        ),
                    )


# ---------------------------------------------------------
# Blender factory without Blender
# ---------------------------------------------------------

class BlenderFactoryTests(
    unittest.TestCase
):
    @staticmethod
    def _vertex(
        x: float,
        y: float,
        z: float,
    ):
        return SimpleNamespace(
            co=SimpleNamespace(
                x=x,
                y=y,
                z=z,
            )
        )

    @staticmethod
    def _mesh_object():
        mesh = SimpleNamespace(
            vertices=[
                BlenderFactoryTests._vertex(
                    0.0,
                    0.0,
                    0.0,
                ),
                BlenderFactoryTests._vertex(
                    3.0,
                    0.0,
                    0.0,
                ),
                BlenderFactoryTests._vertex(
                    0.0,
                    4.0,
                    0.0,
                ),
            ],
            polygons=[
                SimpleNamespace(
                    vertices=(
                        0,
                        1,
                        2,
                    )
                )
            ],
            update=MagicMock(),
        )

        return SimpleNamespace(
            type="MESH",
            data=mesh,
        )

    def test_factory_builds_backend_from_local_mesh(
        self,
    ) -> None:
        obj = (
            self._mesh_object()
        )

        backend = (
            RecordingRaycast()
        )

        config = VisibilityConfig(
            relative_epsilon=0.01,
            absolute_epsilon=0.001,
            ray_length_multiplier=2.0,
        )

        with patch(
            (
                "core.material_visibility."
                "_build_blender_bvh_raycast"
            ),
            return_value=backend,
        ) as build_backend:
            tester = (
                MeshVisibilityTester
                .from_blender_object(
                    obj,
                    config=config,
                )
            )

        obj.data.update.assert_called_once_with()

        build_backend.assert_called_once_with(
            [
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    3.0,
                    0.0,
                    0.0,
                ),
                (
                    0.0,
                    4.0,
                    0.0,
                ),
            ],
            [
                (
                    0,
                    1,
                    2,
                )
            ],
        )

        # Triangle bounding box:
        #
        #     width  = 3
        #     height = 4
        #
        # diagonal = 5
        #
        # epsilon = 5 * 0.01 = 0.05
        # ray     = 5 * 2    = 10
        self.assertAlmostEqual(
            tester.surface_epsilon,
            0.05,
        )

        self.assertAlmostEqual(
            tester.max_distance,
            10.0,
        )

    def test_factory_result_is_immediately_usable(
        self,
    ) -> None:
        obj = (
            self._mesh_object()
        )

        backend = (
            RecordingRaycast()
        )

        with patch(
            (
                "core.material_visibility."
                "_build_blender_bvh_raycast"
            ),
            return_value=backend,
        ):
            tester = (
                MeshVisibilityTester
                .from_blender_object(
                    obj
                )
            )

        visible = (
            tester.is_visible(
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    0.0,
                    -1.0,
                    0.0,
                ),
            )
        )

        self.assertTrue(
            visible
        )

        self.assertEqual(
            len(
                backend.calls
            ),
            1,
        )

    def test_non_mesh_object_is_rejected(
        self,
    ) -> None:
        obj = SimpleNamespace(
            type="LIGHT",
            data=None,
        )

        with self.assertRaises(
            TypeError
        ):
            (
                MeshVisibilityTester
                .from_blender_object(
                    obj
                )
            )

    def test_none_object_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            (
                MeshVisibilityTester
                .from_blender_object(
                    None
                )
            )

    def test_object_without_mesh_data_is_rejected(
        self,
    ) -> None:
        obj = SimpleNamespace(
            type="MESH",
            data=None,
        )

        with self.assertRaises(
            TypeError
        ):
            (
                MeshVisibilityTester
                .from_blender_object(
                    obj
                )
            )

    def test_empty_mesh_is_rejected(
        self,
    ) -> None:
        mesh = SimpleNamespace(
            vertices=[],
            polygons=[],
            update=MagicMock(),
        )

        obj = SimpleNamespace(
            type="MESH",
            data=mesh,
        )

        with self.assertRaises(
            ValueError
        ):
            (
                MeshVisibilityTester
                .from_blender_object(
                    obj
                )
            )

    def test_mesh_without_polygons_is_rejected(
        self,
    ) -> None:
        mesh = SimpleNamespace(
            vertices=[
                self._vertex(
                    0.0,
                    0.0,
                    0.0,
                ),
                self._vertex(
                    1.0,
                    0.0,
                    0.0,
                ),
                self._vertex(
                    0.0,
                    1.0,
                    0.0,
                ),
            ],
            polygons=[],
            update=MagicMock(),
        )

        obj = SimpleNamespace(
            type="MESH",
            data=mesh,
        )

        with self.assertRaises(
            ValueError
        ):
            (
                MeshVisibilityTester
                .from_blender_object(
                    obj
                )
            )

    def test_degenerate_polygon_is_ignored(
        self,
    ) -> None:
        mesh = SimpleNamespace(
            vertices=[
                self._vertex(
                    0.0,
                    0.0,
                    0.0,
                ),
                self._vertex(
                    1.0,
                    0.0,
                    0.0,
                ),
            ],
            polygons=[
                SimpleNamespace(
                    vertices=(
                        0,
                        1,
                    )
                )
            ],
            update=MagicMock(),
        )

        obj = SimpleNamespace(
            type="MESH",
            data=mesh,
        )

        with self.assertRaises(
            ValueError
        ):
            (
                MeshVisibilityTester
                .from_blender_object(
                    obj
                )
            )


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------

if __name__ == "__main__":
    unittest.main()