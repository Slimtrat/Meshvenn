from array import array
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.contour_surface import ContourSurface, sample_mask_gradient
from core.geometry_contracts import GeometryProjectionSpace
from core.image_mask import BinaryMask
from core.projection_math import compile_projection, surface_position_to_normalized
from core.sdf.mask import SignedDistanceMask
from core.sdf.projection import SDFProjection
from core.surface_refinement import refine_native_surface
from core.surface_safety import constrain_faces, _normal, _dot
from tests.test_surface_refinement import mesh, octahedron


def analytic_projection(az=0, el=0, flip=False, width=7, height=5, fn=None):
    transform = compile_projection(azimuth_degrees=az, elevation_degrees=el, flip_x=flip)
    fn = fn or (lambda u, v: .7*u-.4*v+.2)
    field = SignedDistanceMask(width, height,
                              array('f', (fn(x/max(1,width-1), y/max(1,height-1))
                                          for y in range(height) for x in range(width))),
                              transform.horizontal_extent, transform.vertical_extent, 1)
    return SDFProjection('analytic', transform, field)


class ContourSurfaceTests(unittest.TestCase):
    def test_mask_values_and_exact_gradient_inside_and_outside(self):
        for width,height in ((7,5),(1,5),(7,1),(1,1)):
            field = analytic_projection(width=width,height=height).field
            for u,v in ((.23,.61),(1.2,.36),(-.2,.7),(.4,1.3),(.4,-.5),(-.2,1.3)):
                with self.subTest(size=(width,height),uv=(u,v)):
                    value,du,dv = sample_mask_gradient(field,u,v)
                    self.assertAlmostEqual(value,field.sample_uv(u,v),places=7)
                    delta = 1e-6
                    self.assertAlmostEqual(du,(field.sample_uv(u+delta,v)-field.sample_uv(u-delta,v))/(2*delta),places=6)
                    self.assertAlmostEqual(dv,(field.sample_uv(u,v+delta)-field.sample_uv(u,v-delta))/(2*delta),places=6)
        field = analytic_projection().field
        self.assertAlmostEqual(sample_mask_gradient(field,1,1)[1],.7,places=6)
        self.assertAlmostEqual(sample_mask_gradient(field,1,1)[2],-.4,places=6)

    def test_projection_gradient_matches_finite_differences(self):
        for az,el in ((0,0),(90,0),(32,21),(57,-43),(0,90),(0,-90)):
            for flip in (False,True):
                for centered in (False,True):
                    space = GeometryProjectionSpace(20,30,40,voxel_size=.25,center_xy=centered)
                    projection = analytic_projection(az,el,flip)
                    surface = ContourSurface((projection,projection),space)
                    for point in ((.73,.21,4.31),(-12.4,10.2,13.7)):
                        with self.subTest(angles=(az,el),flip=flip,centered=centered,point=point):
                            value,g = surface.sample(point)
                            self.assertAlmostEqual(value,projection.sample(surface_position_to_normalized(
                                point,**space.as_projection_kwargs())),places=7)
                            for k in range(3):
                                a,b = list(point),list(point)
                                a[k] += 1e-5
                                b[k] -= 1e-5
                                numeric = (surface.sample(a)[0]-surface.sample(b)[0])/2e-5
                                self.assertAlmostEqual(g[k],numeric,places=6)

    def test_hard_intersection_selects_active_view(self):
        a,b = analytic_projection(),analytic_projection(90,fn=lambda u,v: u+3)
        surface = ContourSurface((a,b),GeometryProjectionSpace(10,10,10))
        point = (.2,.3,5.4)
        expected = b.sample(surface_position_to_normalized(point,**surface.space.as_projection_kwargs()))
        self.assertAlmostEqual(surface.sample(point)[0],expected)
        self.assertAlmostEqual(surface.sample(point)[1][1],.1,places=6)

    def test_newton_fit_is_deterministic_and_bounded(self):
        p = analytic_projection(fn=lambda u,v: v-.5)
        surface = ContourSurface((p,p),GeometryProjectionSpace(10,10,10))
        for point in ((.2,.3,5.4),(.2,.3,4.6),(.2,.3,8)):
            q = surface.project(point,point,.75)
            self.assertEqual(q,surface.project(point,point,.75))
            self.assertLess(abs(surface.sample(q)[0]),abs(surface.sample(point)[0]))
            self.assertLessEqual(math.dist(point,q),.750000001)
        self.assertAlmostEqual(surface.project((.2,.3,5.4),(.2,.3,5.4),.75)[2],5,places=6)
        self.assertLessEqual(math.dist(surface.project((0,0,8),(0,0,5),.75,iterations=0),(0,0,5)),.75)
        flat = analytic_projection(fn=lambda u,v: 1)
        constant = ContourSurface((flat,flat),surface.space)
        self.assertEqual(constant.project((0,0,5),(0,0,5),.75),(0,0,5))
        self.assertIsNone(constant.residual([(0,0,5)]))
        self.assertEqual(constant.residual_summary([(0,0,5)])["valid_samples"],0)

    def test_validation_and_budget_precede_distance_allocation(self):
        space = GeometryProjectionSpace(10,10,10)
        view = SimpleNamespace(mask=BinaryMask(3,3,b'\1'*9),azimuth_degrees=0,elevation_degrees=0)
        for views in ((view,), (view,SimpleNamespace(mask=BinaryMask(3,3,b'\0'*9))),
                      (view,SimpleNamespace(mask=None)),
                      (view,SimpleNamespace(mask=view.mask,azimuth_degrees=math.nan,elevation_degrees=0))):
            with self.subTest(views=views), patch.object(SDFProjection,'from_source_view') as build:
                with self.assertRaises((ValueError,TypeError)):
                    ContourSurface.from_views(views,space)
                build.assert_not_called()
        with patch('core.contour_surface.MAX_TOTAL_PIXELS',17), patch.object(SDFProjection,'from_source_view') as build:
            with self.assertRaisesRegex(ValueError,'budget'):
                ContourSurface.from_views((view,view),space)
            build.assert_not_called()
        with patch('core.contour_surface.MAX_VIEW_PIXELS',8):
            with self.assertRaisesRegex(ValueError,'budget'):
                ContourSurface.from_views((view,view),space)
        surface = ContourSurface.from_views((view,view),space)
        for options in ({'limit':0},{'limit':math.nan},{'limit':1,'iterations':17},
                        {'limit':1,'iterations':True}):
            with self.assertRaises(ValueError):
                surface.project((0,0,5),(0,0,5),**options)
        for point in ((0,0),(0,0,math.inf)):
            with self.assertRaises(ValueError):
                surface.sample(point)
        with self.assertRaises(ValueError):
            sample_mask_gradient(surface.projections[0].field,math.nan,.5)

    def test_terraced_plane_reduces_contour_error_and_keeps_open_boundary(self):
        size = 9
        original = mesh([(x-4,y-4,5+.15*(-1)**(x+y)) for y in range(size) for x in range(size)],
                        [(y*size+x,y*size+x+1,(y+1)*size+x+1,(y+1)*size+x)
                         for y in range(size-1) for x in range(size-1)])
        p = analytic_projection(fn=lambda u,v: v-.5)
        surface = ContourSurface((p,p),GeometryProjectionSpace(10,10,10))
        result,report = refine_native_surface(original,voxel_size=1,mode='organic',contour_surface=surface)
        self.assertEqual(report['algorithm'],'contour-taubin-v2')
        self.assertLess(report['mean_contour_residual_after_in_voxels'],report['mean_contour_residual_before_in_voxels']*.6)
        self.assertLess(report['roughness_after_in_voxels'],report['roughness_before_in_voxels'])
        self.assertIs(result.indices,original.indices)
        for i in range(size*size):
            if i%size in (0,size-1) or i//size in (0,size-1):
                self.assertEqual(result.vertices[i*3:i*3+3],original.vertices[i*3:i*3+3])
        with self.assertRaisesRegex(ValueError,'voxel sizes'):
            refine_native_surface(original,voxel_size=.5,mode='organic',contour_surface=surface)

    def test_local_guard_does_not_reduce_safe_remote_faces(self):
        original = [(0,0,0),(1,0,0),(0,1,0),(3,0,0),(4,0,0),(3,1,0)]
        candidate = original[:]
        candidate[2] = (0,-.2,0)  # flipped first triangle
        candidate[3] = (3,0,.2)  # safe second triangle
        triangles = [(0,1,2),(3,4,5)]
        points,limited = constrain_faces(original,candidate,triangles,2)
        self.assertEqual(limited,3)
        self.assertAlmostEqual(points[3][2],.2,places=7)
        for tri in triangles:
            n = _normal(original,tri)
            self.assertGreaterEqual(_dot(_normal(points,tri),n),.1*_dot(n,n))

    def test_contour_fit_still_checks_closed_components_independently(self):
        a,b = octahedron(.5,(0,0,1)),octahedron(.1,(.8,0,1))
        original = mesh([tuple(a.vertices[i:i+3]) for i in range(0,18,3)] +
                        [tuple(b.vertices[i:i+3]) for i in range(0,18,3)],
                        [tuple(a.indices[i:i+3]) for i in range(0,24,3)] +
                        [tuple(j+6 for j in b.indices[i:i+3]) for i in range(0,24,3)])
        p = analytic_projection(fn=lambda u,v: v-.5)
        surface = ContourSurface((p,p),GeometryProjectionSpace(10,10,10,voxel_size=.2))
        _,report = refine_native_surface(original,voxel_size=.2,mode='organic',contour_surface=surface)
        self.assertEqual(report['volume_checked_component_count'],2)
        self.assertLessEqual(report['maximum_component_volume_drift'],.02)
        self.assertLessEqual(report['maximum_displacement_in_voxels'],.75)
        self.assertTrue(report['face_orientation_preserved'])

    def test_batch_cache_tracks_pixels_angles_and_flips(self):
        space = GeometryProjectionSpace(10,10,10)
        view = SimpleNamespace(mask=BinaryMask(3,3,b'\1'*9),azimuth_degrees=0,elevation_degrees=0,flip_x=False)
        cache = {}
        with patch.object(SDFProjection,'from_source_view',wraps=SDFProjection.from_source_view) as build:
            first = ContourSurface.from_views((view,view),space,cache=cache)
            second = ContourSurface.from_views((view,view),space,cache=cache)
            self.assertIs(first.projections[0],second.projections[0])
            self.assertEqual(build.call_count,1)
            view.flip_x = True
            ContourSurface.from_views((view,view),space,cache=cache)
            view.azimuth_degrees = 45
            ContourSurface.from_views((view,view),space,cache=cache)
            view.mask = BinaryMask(3,3,b'\1'*8+b'\0')
            ContourSurface.from_views((view,view),space,cache=cache)
            self.assertEqual(build.call_count,4)
