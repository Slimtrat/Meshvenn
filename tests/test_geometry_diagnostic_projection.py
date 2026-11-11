from __future__ import annotations

import math
import os
import random
import time
import unittest
from pathlib import Path

from core.diagnostic_contracts import CameraDeclaration, CameraProjection, Region, VerificationStatus
from core.geometry_diagnostics.metrics import MaskComparison, _distance_squared, compare_masks
from core.geometry_diagnostics.projection import (aligned_mask, nearest_mask_pixel,
    project_voxel_center, projection_tolerance_pixels, reproject_volume)
from core.image_mask import BinaryMask
from core.native_bridge import NativeCore, NativeProjection, NativeVolume
from core.projection_alignment import ProjectionAlignment
from core.projection_math import ProjectedPoint


def camera(azimuth=0.0, elevation=0.0, flip=False):
    return CameraDeclaration(CameraProjection.ORTHOGRAPHIC, azimuth, elevation, flip)


def volume(width=8, depth=8, height=8, predicate=lambda x, y, z: True):
    data = bytes(bool(predicate(x, y, z)) for z in range(height)
                 for y in range(depth) for x in range(width))
    return NativeVolume(width, depth, height, data, sum(data), None)


def mask(width, height, predicate):
    return BinaryMask(width, height, bytes(bool(predicate(x, y))
                                         for y in range(height) for x in range(width)))


class GeometryProjectionTests(unittest.TestCase):
    def test_native_centres_include_endpoints_and_cardinal_flip(self):
        v = volume(8, 9, 10)
        self.assertEqual(project_voxel_center(v, camera(), 0, 4, 0), ProjectedPoint(0, 0))
        self.assertEqual(project_voxel_center(v, camera(), 7, 4, 9), ProjectedPoint(1, 1))
        self.assertAlmostEqual(project_voxel_center(v, camera(90), 0, 8, 0).u, 1)
        self.assertEqual(project_voxel_center(v, camera(flip=True), 0, 4, 0), ProjectedPoint(1, 0))
        self.assertEqual(nearest_mask_pixel(ProjectedPoint(.25, .75), width=3, height=3), (1, 2))
        self.assertIsNone(nearest_mask_pixel(ProjectedPoint(-1e-8, .5), width=3, height=3))

    def test_finite_cells_fill_raster_larger_than_native_volume_without_holes(self):
        v = volume(predicate=lambda x, y, z: 2 <= x <= 5 and 1 <= z <= 6)
        result = reproject_volume(v, camera(), width=113, height=79)
        # Native cell limits x=[1.5/7,5.5/7], z=[.5/7,6.5/7].
        expected = mask(113, 79, lambda x, y:
            x + .5 > 112 * 1.5 / 7 and x - .5 < 112 * 5.5 / 7
            and y + .5 > 78 * .5 / 7 and y - .5 < 78 * 6.5 / 7)
        self.assertEqual(result, expected)
        self.assertEqual(reproject_volume(v, camera(flip=True), width=113, height=79), result.flipped_x())

    def test_full_oblique_elevated_cube_has_convex_silhouette_not_rectangle(self):
        result = reproject_volume(volume(), camera(37, 29), width=91, height=57)
        self.assertFalse(result.get(0, 0))
        self.assertFalse(result.get(90, 56))
        self.assertTrue(result.get(45, 28))
        self.assertLess(result.occupied_count, 91 * 57)
        # One coarse cell is exactly the same complete normalized cube.
        self.assertEqual(result, reproject_volume(volume(1, 1, 1), camera(37, 29), width=91, height=57))

    def test_single_cell_footprint_matches_independent_polygon_square_sat(self):
        az, el = math.radians(31), math.radians(23)
        h = abs(math.cos(az)) + abs(math.sin(az))
        ve = h * abs(math.sin(el)) + abs(math.cos(el))
        projected = []
        for x in (2.5 / 7 * 2 - 1, 3.5 / 7 * 2 - 1):
            for y in (4.5 / 7 * 2 - 1, 5.5 / 7 * 2 - 1):
                for z in (3.5 / 7 * 2 - 1, 4.5 / 7 * 2 - 1):
                    px = x * math.cos(az) + y * math.sin(az)
                    py = x * math.sin(az) * math.sin(el) - y * math.cos(az) * math.sin(el) + z * math.cos(el)
                    projected.append(((px / h + 1) * 13, (py / ve + 1) * 9))
        # A projected cuboid is a zonotope: SAT normals are perpendicular to its
        # three projected edge directions plus the raster square's two axes.
        directions = [(math.cos(az) / h * 13, math.sin(az) * math.sin(el) / ve * 9),
                      (math.sin(az) / h * 13, -math.cos(az) * math.sin(el) / ve * 9),
                      (0, math.cos(el) / ve * 9)]
        axes = [(1, 0), (0, 1)] + [(-dy, dx) for dx, dy in directions]
        def intersects(x, y):
            square = [(x + dx, y + dy) for dx in (-.5, .5) for dy in (-.5, .5)]
            for nx, ny in axes:
                p = [nx * a + ny * b for a, b in projected]
                q = [nx * a + ny * b for a, b in square]
                if max(p) <= min(q) + 1e-9 or max(q) <= min(p) + 1e-9:
                    return False
            return True
        v = volume(predicate=lambda x, y, z: (x, y, z) == (3, 5, 4))
        self.assertEqual(reproject_volume(v, camera(31, 23), width=27, height=19), mask(27, 19, intersects))

    def test_no_bridge_across_disconnected_cells(self):
        v = volume(predicate=lambda x, y, z: x in (0, 7) and z in (0, 7))
        result = reproject_volume(v, camera(), width=65, height=33)
        self.assertFalse(result.get(32, 16))
        for x, y in ((0, 0), (64, 0), (0, 32), (64, 32)):
            self.assertTrue(result.get(x, y))

    def test_single_pixel_axes_and_alignment_delegate(self):
        v = volume(predicate=lambda x, y, z: x == 7 and z == 7)
        self.assertEqual(reproject_volume(v, camera(), width=1, height=1).values, b"\x01")
        source = mask(19, 13, lambda x, y: x < y)
        alignment = ProjectionAlignment(.1, -.2, 1.5)
        self.assertEqual(aligned_mask(source, alignment), alignment.align_mask(source))
        self.assertGreater(projection_tolerance_pixels(volume(), camera(37, 29), 256, 128), 1)

    def test_original_megapixel_alignment_preserves_fine_detail_without_resizing(self):
        source = mask(1024, 1024, lambda x, y: (x, y) == (513, 519))
        self.assertIs(aligned_mask(source, ProjectionAlignment()), source)
        shifted = aligned_mask(source, ProjectionAlignment(offset_u=1 / 1023))
        self.assertEqual((shifted.width, shifted.height, shifted.occupied_count), (1024, 1024, 1))
        self.assertTrue(shifted.get(514, 519))

    def test_budgets_cancel_and_invalid_native_storage(self):
        v = volume()
        with self.assertRaisesRegex(ValueError, "work budget"):
            reproject_volume(v, camera(), width=31, height=19, max_work=1)
        with self.assertRaises(TimeoutError):
            reproject_volume(v, camera(), width=31, height=19, deadline=time.monotonic() - 1)
        with self.assertRaises(InterruptedError):
            reproject_volume(v, camera(), width=31, height=19, cancel=lambda: True)
        with self.assertRaisesRegex(ValueError, "count consistent"):
            reproject_volume(NativeVolume(1, 1, 1, b"\x01", 0, None), camera(), width=3, height=3)

    def test_checkerboard_cancellation_is_checked_during_run_projection(self):
        checkerboard = volume(64, 64, 64, lambda x, y, z: (x + y + z) % 2)
        checks = []
        def cancel():
            checks.append(True)
            return len(checks) == 10
        with self.assertRaises(InterruptedError):
            reproject_volume(checkerboard, camera(31, 23), width=256, height=256, cancel=cancel)
        self.assertEqual(len(checks), 10)

    @unittest.skipUnless(os.environ.get("MESHVENN_TEST_NATIVE_DLL"), "Set MESHVENN_TEST_NATIVE_DLL to audit real native sampler.")
    def test_all_centres_match_real_native_cardinal_oblique_elevated_and_flipped(self):
        native = NativeCore(Path(os.environ["MESHVENN_TEST_NATIVE_DLL"]))
        source = mask(19, 17, lambda x, y: ((x * 17 + y * 13) % 11) < 6)
        for declared in (camera(), camera(90), camera(37, 29), camera(128, -41, True)):
            with self.subTest(camera=declared), native.create_session(resolution=8, thread_count=1) as session:
                session.apply_projection(NativeProjection(source, declared.azimuth_degrees,
                    declared.elevation_degrees, declared.flip_x))
                actual = session.snapshot()
                expected = []
                for z in range(8):
                    for y in range(8):
                        for x in range(8):
                            point = project_voxel_center(actual, declared, x, y, z)
                            pixel = nearest_mask_pixel(point, width=source.width, height=source.height)
                            expected.append(bool(pixel and source.get(*pixel)))
                self.assertEqual(actual.values, bytes(expected))


class GeometryMetricTests(unittest.TestCase):
    def test_counts_empty_conventions_and_roundtrip(self):
        expected = mask(5, 3, lambda x, y: x < 3)
        actual = mask(5, 3, lambda x, y: x > 1)
        result = compare_masks(expected, actual)
        self.assertEqual((result.intersection_pixels, result.missing_pixels, result.extraneous_pixels), (3, 6, 6))
        self.assertAlmostEqual(result.iou, .2)
        self.assertAlmostEqual(result.precision, 1 / 3)
        self.assertAlmostEqual(result.recall, 1 / 3)
        self.assertEqual(MaskComparison.from_dict(result.to_dict()), result)
        empty = mask(5, 3, lambda x, y: False)
        self.assertEqual(compare_masks(empty, empty).iou, 1)
        self.assertIsNone(compare_masks(empty, actual).contour_mean_pixels)
        self.assertEqual(compare_masks(expected, empty).missing_beyond_tolerance_pixels, 9)

    def test_exact_edt_matches_independent_all_pairs_on_random_rasters(self):
        rng = random.Random(17)
        for _ in range(10):
            source = mask(9, 7, lambda x, y: rng.random() < .2)
            points = [(x, y) for y in range(7) for x in range(9) if source.get(x, y)]
            expected = [min(((x - px) ** 2 + (y - py) ** 2 for px, py in points), default=math.inf)
                        for y in range(7) for x in range(9)]
            self.assertEqual(_distance_squared(source.values, 9, 7, None, None), expected)

    def test_contour_distance_is_symmetric_exact_euclidean(self):
        a = mask(9, 9, lambda x, y: (x, y) == (2, 2))
        b = mask(9, 9, lambda x, y: (x, y) == (5, 6))
        result = compare_masks(a, b)
        self.assertEqual(result.contour_mean_pixels, 5)
        self.assertEqual(result.contour_max_pixels, 5)
        self.assertEqual(compare_masks(b, a).contour_max_pixels, 5)

    def test_high_iou_cannot_hide_resolved_missing_detached_component(self):
        expected = mask(64, 64, lambda x, y: (2 <= x <= 41 and 2 <= y <= 41)
                        or (51 <= x <= 54 and 51 <= y <= 54))
        actual = mask(64, 64, lambda x, y: 2 <= x <= 41 and 2 <= y <= 41)
        result = compare_masks(expected, actual)
        self.assertGreater(result.iou, .99)
        self.assertEqual(result.component_count, 2)
        self.assertEqual(result.components[1].status, VerificationStatus.FAIL)
        self.assertEqual(result.components[1].beyond_tolerance_pixels, 16)
        self.assertEqual(result.missing_regions[0].pixel_count, 16)

    def test_subresolution_components_and_named_regions_are_unknown_even_if_matching(self):
        source = mask(32, 32, lambda x, y: (x, y) == (16, 16))
        region = Region("front", "important detail", (.49, .49, .54, .54))
        result = compare_masks(source, source, regions=(region,), resolution_tolerance_pixels=1)
        self.assertEqual(result.components[0].status, VerificationStatus.UNKNOWN)
        self.assertEqual(result.important_regions[0].status, VerificationStatus.UNKNOWN)

    def test_nearby_deficit_is_unknown_within_resolution_tolerance(self):
        expected = mask(20, 20, lambda x, y: 2 <= x <= 17 and 2 <= y <= 17)
        actual = mask(20, 20, lambda x, y: 3 <= x <= 16 and 3 <= y <= 16)
        result = compare_masks(expected, actual, resolution_tolerance_pixels=1.5)
        self.assertGreater(result.missing_pixels, 0)
        self.assertEqual(result.missing_beyond_tolerance_pixels, 0)
        self.assertEqual(result.components[0].status, VerificationStatus.UNKNOWN)

    def test_truncated_component_count_and_work_limits_are_explicit(self):
        source = mask(11, 11, lambda x, y: x % 2 == 0 and y % 2 == 0)
        result = compare_masks(source, source, max_regions=4)
        self.assertEqual(result.component_count, 36)
        self.assertTrue(result.components_truncated)
        self.assertEqual(len(result.components), 4)
        with self.assertRaisesRegex(ValueError, "work budget"):
            compare_masks(source, source, max_work=1)
        with self.assertRaises(InterruptedError):
            compare_masks(source, source, cancel=lambda: True)
        with self.assertRaises(TimeoutError):
            compare_masks(source, source, deadline=time.monotonic() - 1)

    def test_cancellation_is_checked_during_distance_transform(self):
        source = mask(128, 128, lambda x, y: 20 < x < 100 and 20 < y < 100)
        checks = []
        def cancel():
            checks.append(True)
            return len(checks) == 5
        with self.assertRaises(InterruptedError):
            compare_masks(source, source, cancel=cancel)
        self.assertEqual(len(checks), 5)


if __name__ == "__main__":
    unittest.main()
