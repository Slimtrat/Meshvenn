import math
import unittest

from core.projection_frame import native_projection_frame, native_projection_axes
from core.projection_math import compile_projection, project_normalized_point, NormalizedPoint


class ProjectionFrameTests(unittest.TestCase):
    def test_camera_matches_native_uv_including_poles(self):
        for az,el in ((0,0),(45,0),(90,0),(225,0),(315,0),(0,90),(0,-90),(32,21)):
            with self.subTest(az=az,el=el):
                transform = compile_projection(azimuth_degrees=az,elevation_degrees=el)
                right,up,backward = native_projection_axes(az,el)
                scale,aspect = native_projection_frame(2,az,el,148,164)
                effective_aspect=aspect*148/164
                width=scale*min(1,effective_aspect)
                # Blender ortho_scale is the larger span.
                height=scale*min(1,1/effective_aspect)
                for point in ((.6,-.3,.8),(-.2,.7,-.4)):
                    uv=project_normalized_point(NormalizedPoint(*point),transform)
                    self.assertAlmostEqual(.5+sum(p*r for p,r in zip(point,right))/width,uv.u)
                    self.assertAlmostEqual(.5+sum(p*r for p,r in zip(point,up))/height,uv.v)
                for axis in (right,up,backward):
                    self.assertAlmostEqual(sum(x*x for x in axis),1)
                self.assertAlmostEqual(sum(x*y for x,y in zip(right,up)),0)

    def test_frame_scales_with_domain_not_cell_aspect(self):
        scale,aspect=native_projection_frame(2,45,0,148,164)
        self.assertAlmostEqual(scale,2*math.sqrt(2))
        self.assertAlmostEqual(aspect,math.sqrt(2)*164/148)
        self.assertEqual(native_projection_frame(4,45,0,148,164),(scale*2,aspect))

    def test_invalid_frame_is_rejected(self):
        for side,az,el,w,h in ((0,0,0,1,1),(1,math.nan,0,1,1),(1,0,math.inf,1,1),(1,0,0,0,1)):
            with self.assertRaises(ValueError):
                native_projection_frame(side,az,el,w,h)
