"""Independent analytic rays and actual pure-BVH visibility correspondences."""
from __future__ import annotations

import importlib
import math
import sys
import time
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

from core.appearance_diagnostics.correspondence import SurfaceSampler
from core.appearance_diagnostics.surface import SurfaceMesh
from core.diagnostic_contracts import ArtifactReference, CameraDeclaration, ViewRevision
from core.material_visibility import MeshVisibilityTester
from core.projection_alignment import ProjectionAlignment
from core.projection_frame import native_projection_axes
from core.projection_math import NormalizedPoint, compile_projection, direction_to_camera, project_normalized_point
from core.projection_math.projection import projection_aligned_axes, unproject_normalized_uv

PROOF = ArtifactReference("analytic-surface", "a" * 64, "application/json")


def view(name="target", azimuth=0., elevation=0., flip=False, alignment=None, verified=True):
    return ViewRevision(name, 1, None, None,
        CameraDeclaration("orthographic", azimuth, elevation, flip, verified, PROOF if verified else None),
        alignment or ProjectionAlignment())


def plane(*, reverse=False, duplicate=False):
    triangles = ((0, 1, 2), (0, 2, 3))
    if reverse:
        triangles = tuple(tuple(reversed(t)) for t in triangles)
    if duplicate:
        triangles += triangles
    return SurfaceMesh(((-.8, 0., -.8), (.8, 0., -.8), (.8, 0., .8), (-.8, 0., .8)), triangles, PROOF)


def merged_planes(other_vertices):
    original = plane()
    return SurfaceMesh(original.vertices + tuple(other_vertices), original.triangles + ((4, 5, 6), (4, 6, 7)), PROOF)


class ProjectionAlignedRayTests(unittest.TestCase):
    def test_native_null_space_preserves_uv_for_oblique_poles_and_flips(self):
        for az, el in ((0, 30), (37, -23), (-128, 41), (0, 90), (151, -90), (359, 89.999)):
            for flip in (False, True):
                transform = compile_projection(azimuth_degrees=az, elevation_degrees=el, flip_x=flip)
                right, up, direction = projection_aligned_axes(transform)
                expected_axes = native_projection_axes(az, el)
                for actual, expected in zip((right, up, direction), expected_axes):
                    for a, b in zip(actual, expected):
                        self.assertAlmostEqual(a, b, places=13)
                for point in (NormalizedPoint(.2, -.31, .43), NormalizedPoint(-.7, .29, -.13)):
                    original = project_normalized_point(point, transform)
                    for distance in (-1., .37, 2.):
                        shifted = project_normalized_point(NormalizedPoint(
                            *(coordinate+distance*delta for coordinate, delta in zip((point.x, point.y, point.z), direction))), transform)
                        self.assertAlmostEqual(shifted.u, original.u, places=12)
                        self.assertAlmostEqual(shifted.v, original.v, places=12)

    def test_legacy_positive_elevation_direction_is_explicitly_not_used_or_changed(self):
        transform = compile_projection(azimuth_degrees=0, elevation_degrees=30)
        legacy = direction_to_camera(azimuth_degrees=0, elevation_degrees=30)
        native = projection_aligned_axes(transform)[2]
        self.assertAlmostEqual(legacy[2], .5)
        self.assertAlmostEqual(native[2], -.5)
        moved = project_normalized_point(NormalizedPoint(*legacy), transform)
        self.assertNotAlmostEqual(moved.v, .5)

    def test_inverse_uv_and_alignment_are_exact_at_every_supported_orientation(self):
        alignment = ProjectionAlignment(.13, -.08, 1.2)
        for az, el in ((0, 0), (41, 27), (73, -54), (12, 90), (185, -90)):
            for flip in (False, True):
                transform = compile_projection(azimuth_degrees=az, elevation_degrees=el, flip_x=flip)
                for original in ((0., 0.), (.27, .63), (1., 1.)):
                    aligned = alignment.aligned_uv(*original)
                    recovered = alignment.source_uv(*aligned)
                    for a, b in zip(original, recovered):
                        self.assertAlmostEqual(a, b, places=14)
                    for depth in (-2., 0., 4.):
                        point = unproject_normalized_uv(*aligned, transform, depth=depth)
                        projected = project_normalized_point(point, transform)
                        self.assertAlmostEqual(projected.u, aligned[0], places=12)
                        self.assertAlmostEqual(projected.v, aligned[1], places=12)


class SurfaceContractTests(unittest.TestCase):
    def test_surface_is_immutable_strict_and_content_hashed(self):
        mesh = plane()
        self.assertEqual(SurfaceMesh.from_json(mesh.to_json()), mesh)
        self.assertEqual(len(mesh.sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            mesh.vertices = ()
        for change in ({"vertices": [[float("nan"), 0, 0]] * 4},
                       {"triangles": [[0, 1, 12]]}, {"triangles": [[0, 0, 1]]},
                       {"vertices": [[-2, 0, -1], [1, 0, -1], [1, 0, 1], [-1, 0, 1]]},
                       {"binding_sha256": "invalid"}, {"sha256": "b" * 64}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                SurfaceMesh.from_dict(mesh.to_dict() | change)

    def test_blender_visibility_backend_is_not_imported_by_the_pure_facade(self):
        # The domain/tester remain usable with a callback, while legacy Blender
        # construction keeps its callable adapter available lazily.
        facade = importlib.import_module("core.material_visibility")
        self.assertTrue(callable(facade._build_blender_bvh_raycast))
        tester = MeshVisibilityTester(lambda *args: None, surface_epsilon=1e-6, max_distance=8)
        self.assertTrue(tester.query((0, 0, 0), (0, -1, 0)).visible)


class SurfaceCorrespondenceTests(unittest.TestCase):
    def test_plane_hits_empty_background_and_shared_diagonal_are_correct(self):
        result = SurfaceSampler(plane()).map_views(view(), (view("reference"),), width=9, height=9)
        self.assertEqual(result.pixels[0].state, "no_hit")
        center = result.pixels[4*9+4]
        self.assertEqual(center.state, "visible")
        self.assertEqual(center.target_original_uv, (.5, .5))
        for coordinate in center.point3d:
            self.assertAlmostEqual(coordinate, 0)
        self.assertEqual(center.references[0].state, "visible")
        self.assertEqual(center.references[0].original_uv, (.5, .5))

    def test_original_grid_oblique_alignment_and_flip_match_independent_plane_algebra(self):
        az, el, alignment = math.radians(37), math.radians(23), ProjectionAlignment(.1, -.07, .9)
        target = view(azimuth=37, elevation=23, flip=True, alignment=alignment)
        reference = view("reference", -21, -17, True, ProjectionAlignment(-.04, .08, 1.1))
        result = SurfaceSampler(plane()).map_views(target, (reference,), width=17, height=13)
        right = (math.cos(az), math.sin(az), 0)
        up = (math.sin(az)*math.sin(el), -math.cos(az)*math.sin(el), math.cos(el))
        direction = (math.sin(az)*math.cos(el), -math.cos(az)*math.cos(el), -math.sin(el))
        horizontal = abs(math.cos(az))+abs(math.sin(az))
        vertical = horizontal*abs(math.sin(el))+abs(math.cos(el))
        visible = 0
        for pixel in result.pixels:
            u, v = alignment.aligned_uv(pixel.x/16, pixel.y/12)
            self.assertEqual(pixel.target_original_uv, (pixel.x/16, pixel.y/12))
            p = tuple((1-2*u)*horizontal*right[i]+(2*v-1)*vertical*up[i] for i in range(3))
            depth = -p[1]/direction[1]
            point = tuple(p[i]+depth*direction[i] for i in range(3))
            inside = 0 <= u <= 1 and 0 <= v <= 1 and abs(point[0]) <= .8+1e-10 and abs(point[2]) <= .8+1e-10
            if inside:
                visible += 1
                self.assertEqual(pixel.state, "visible")
                for actual, expected in zip(pixel.point3d, point):
                    self.assertAlmostEqual(actual, expected, places=10)
                projected = project_normalized_point(NormalizedPoint(*point), reference.camera.transform)
                for actual, expected in zip(pixel.references[0].original_uv, reference.alignment.source_uv(projected.u, projected.v)):
                    self.assertAlmostEqual(actual, expected, places=11)
            else:
                self.assertIn(pixel.state, ("no_hit", "outside"))
        self.assertGreater(visible, 20)

    def test_true_occluder_is_distinct_from_backface_grazing_and_outside(self):
        mesh = merged_planes(((.4, -.5, -.4), (.8, -.5, -.4), (.8, -.5, .4), (.4, -.5, .4)))
        references = (view("blocked", 45), view("back", 180), view("grazing", 87),
                      view("outside", alignment=ProjectionAlignment(.5, 0, .25)))
        result = SurfaceSampler(mesh).map_views(view(), references, width=3, height=3)
        center = result.pixels[4]
        self.assertEqual(center.state, "visible")
        states = {reference.view_id: reference for reference in center.references}
        self.assertEqual(states["blocked"].state, "occluded")
        self.assertTrue(states["blocked"].occluded)
        self.assertIn(states["blocked"].occluder_triangle, (2, 3))
        self.assertEqual(states["blocked"].projected_uv, (.5, .5))
        self.assertEqual(states["blocked"].original_uv, (.5, .5))
        self.assertEqual(states["back"].state, "backfacing")
        self.assertTrue(states["back"].backfacing)
        self.assertEqual(states["grazing"].state, "grazing")
        self.assertTrue(states["grazing"].grazing)
        self.assertEqual(states["outside"].state, "outside")

    def test_winding_is_never_corrected_and_overlapping_faces_remain_ambiguous(self):
        reversed_map = SurfaceSampler(plane(reverse=True)).map_views(view(), (), width=1, height=1)
        self.assertEqual(reversed_map.pixels[0].state, "backfacing")
        self.assertEqual(reversed_map.pixels[0].references, ())
        duplicate = SurfaceSampler(plane(duplicate=True)).map_views(view(), (), width=1, height=1)
        self.assertEqual(duplicate.pixels[0].state, "ambiguous")
        self.assertIsNone(duplicate.pixels[0].triangle_index)

    def test_reverse_maps_accept_a_canonical_reference_as_target(self):
        canonical = replace(view("canonical"), role="reference")
        result = SurfaceSampler(plane()).map_views(canonical, (view("observation", 20),), width=3, height=3)
        self.assertEqual(result.target_view_id, "canonical")
        self.assertEqual(result.pixels[4].state, "visible")
        self.assertEqual(result.pixels[4].references[0].view_id, "observation")

    def test_visibility_offset_does_not_silently_pass_a_thin_near_occluder(self):
        mesh = merged_planes(((.5e-6, -1e-6, -.4), (1.5e-6, -1e-6, -.4),
                              (1.5e-6, -1e-6, .4), (.5e-6, -1e-6, .4)))
        result = SurfaceSampler(mesh).map_views(view(), (view("near", 45),), width=1, height=1)
        reference = result.pixels[0].references[0]
        self.assertEqual(reference.state, "numerical_unknown")
        self.assertFalse(reference.visible)

    def test_unverified_camera_and_deadline_cancellation_work_limits_remain_explicit(self):
        result = SurfaceSampler(plane()).map_views(view(verified=False), (), width=2, height=2)
        self.assertTrue(all(pixel.state == "camera_unknown" for pixel in result.pixels))
        with self.assertRaises(TimeoutError):
            SurfaceSampler(plane(), deadline=time.monotonic()-1)
        with self.assertRaises(InterruptedError):
            SurfaceSampler(plane(), cancel=lambda: True)
        with self.assertRaisesRegex(ValueError, "work budget"):
            SurfaceSampler(plane(), max_work=1)
        sampler = SurfaceSampler(plane(), max_work=100)
        with self.assertRaisesRegex(ValueError, "work budget"):
            sampler.map_views(view(), (), width=9, height=9)
        with self.assertRaises(ValueError):
            SurfaceSampler(plane()).map_views(view(), (), width=129, height=1)

    def test_actual_bvh_builds_branches_and_budget_is_shared_between_maps(self):
        vertices = tuple((-.8+1.6*x/16, 0., -.8+1.6*y/16) for y in range(17) for x in range(17))
        triangles = tuple(triangle for y in range(16) for x in range(16)
            for triangle in ((y*17+x, y*17+x+1, (y+1)*17+x+1), (y*17+x, (y+1)*17+x+1, (y+1)*17+x)))
        sampler = SurfaceSampler(SurfaceMesh(vertices, triangles, PROOF), max_work=2_000_000)
        self.assertIsNotNone(sampler.bvh.root.left)
        first = sampler.map_views(view(), (view("reference"),), width=17, height=17)
        second = sampler.map_views(view("second", azimuth=20), (), width=17, height=17)
        self.assertGreater(second.work_units, first.work_units)
        self.assertEqual(first.pixels[8*17+8].state, "visible")
        self.assertLess(second.work_units, 512*17*17)

    def test_cancel_and_deadline_are_checked_during_actual_ray_work(self):
        checks = 0
        def cancel():
            nonlocal checks
            checks += 1
            return checks >= 5
        sampler = SurfaceSampler(plane(), cancel=cancel)
        built = sampler.work_units
        with self.assertRaises(InterruptedError):
            sampler.map_views(view(), (), width=64, height=64)
        self.assertGreater(sampler.work_units, built)
        ticks = iter(range(100))
        with patch("core.appearance_diagnostics.bvh.time.monotonic", side_effect=lambda: next(ticks)):
            sampler = SurfaceSampler(plane(), deadline=4)
            built = sampler.work_units
            with self.assertRaises(TimeoutError):
                sampler.map_views(view(), (), width=64, height=64)
            self.assertGreater(sampler.work_units, built)


if __name__ == "__main__":
    unittest.main()
