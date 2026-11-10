"""Standalone geometry, calibrated projection parity and extension boundaries."""
import ast
from collections import Counter
from dataclasses import asdict
import importlib
import math
from pathlib import Path
import random
import sys
import tomllib
import unittest

FOLDER=Path(__file__).resolve().parents[1]
ROOT=FOLDER.parents[1]
sys.path.insert(0,str(FOLDER.parent))
from meshvenn_sketch.geometry import ViewFrame,dot,extrude
from meshvenn_sketch.polygon import outline,simplify,triangulate


def area(points):return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2


class GeometryTests(unittest.TestCase):
    def test_concave_clockwise_duplicate_and_collinear_contours_triangulate(self):
        raw=((.1,.1),(.8,.1),(.8,.8),(.45,.45),(.1,.8))
        for points in (raw,tuple(reversed(raw)),(*raw,raw[0]),(raw[0],(.45,.1),*raw[1:])):
            clean,faces=triangulate(points)
            self.assertEqual(len(faces),len(clean)-2)
            self.assertAlmostEqual(sum(area(tuple(clean[i] for i in f)) for f in faces),area(raw))

    def test_crossings_holes_touching_nonfinite_and_zero_area_are_refused(self):
        for points in (((0,0),(1,1),(0,1),(1,0)),((0,0),(1,0),(0,0),(0,1)),
                       ((0,0),(.5,0),(1,0)),((0,0),(math.nan,0),(0,1)),((0,0),(1,0))):
            with self.assertRaises(ValueError):outline(points)

    def test_closed_freehand_simplification_preserves_corner_shape(self):
        points=[]
        corners=((.1,.1),(.9,.1),(.9,.9),(.1,.9),(.1,.1))
        for a,b in zip(corners,corners[1:]):
            points.extend((a[0]+(b[0]-a[0])*t/100,a[1]+(b[1]-a[1])*t/100) for t in range(100))
        reduced=outline(simplify(points,(1000,500)))
        self.assertEqual(len(reduced),4)
        self.assertAlmostEqual(area(reduced),.64)

    def test_all_view_angles_alignment_flip_and_anisotropic_ray_roundtrip(self):
        randomizer=random.Random(924)
        for azimuth in (0,37,90,180,270,315):
            for elevation in (-90,-37,0,52,90):
                for flip in (False,True):
                    frame=ViewFrame((-2,-3,1),(4,6,9),azimuth,elevation,flip,.12,-.07,1.3)
                    point=tuple(o+s*randomizer.random() for o,s in zip(frame.minimum,frame.size))
                    uv=frame.project(point)
                    actual=frame.unproject(uv,point)
                    for a,b in zip(actual,point):self.assertAlmostEqual(a,b,places=10)
                    moved=tuple(p+q*1.7 for p,q in zip(point,frame.ray()))
                    for a,b in zip(frame.project(moved),uv):self.assertAlmostEqual(a,b,places=10)

    def test_extrusions_are_closed_outward_and_keep_image_caps(self):
        points=((.1,.2),(.7,.2),(.7,.8),(.4,.55),(.1,.8))
        for azimuth,elevation in ((0,0),(90,0),(180,30),(270,-40),(40,90)):
            for flip in (False,True):
                frame=ViewFrame((-2,-3,0),(4,6,8),azimuth,elevation,flip)
                clean,vertices,faces,uvs=extrude(points,frame,(.1,.2,4),.3,.4)
                edges=Counter(tuple(sorted((a,b))) for f in faces for a,b in zip(f,(*f[1:],f[0])))
                self.assertEqual(set(edges.values()),{2})
                self.assertEqual(len(vertices)-len(edges)+len(faces),2)
                volume=0.
                for f in faces:
                    for i in range(1,len(f)-1):
                        a,b,c=(vertices[j] for j in (f[0],f[i],f[i+1]))
                        volume+=dot(a,(b[1]*c[2]-b[2]*c[1],b[2]*c[0]-b[0]*c[2],b[0]*c[1]-b[1]*c[0]))/6
                self.assertGreater(volume,0)
                self.assertEqual(len(faces),len(uvs))
                for point,uv in zip(vertices[:len(clean)],clean):
                    for a,b in zip(frame.project(point),uv):self.assertAlmostEqual(a,b,places=10)

    def test_invalid_frames_and_depth_are_refused(self):
        for params in ({'size':(4,0,8)},{'elevation':91},{'scale':0},{'azimuth':math.nan},{'flip_x':1}):
            base={'minimum':(0,0,0),'size':(4,6,8)};base.update(params)
            with self.assertRaises(ValueError):ViewFrame(**base)
        for depth in (0,-1,math.nan,math.inf,True):
            with self.assertRaises(ValueError):extrude(((0,0),(1,0),(0,1)),ViewFrame((0,0,0),(1,1,1)),(0,0,0),depth)

    def test_projection_matches_documented_engine_data_contract(self):
        sys.path.insert(0,str(ROOT))
        from core.projection_math import compile_projection,project_surface_position
        from core.projection_alignment import ProjectionAlignment
        for centred in (False,True):
            for az,el,flip in ((0,0,False),(45,31,False),(90,-20,True),(180,0,True),(270,90,False)):
                w,d,h,voxel=40,60,80,.2
                minimum=(-w*voxel/2,-d*voxel/2,0) if centred else (0,0,0)
                frame=ViewFrame(minimum,(w*voxel,d*voxel,h*voxel),az,el,flip,.1,-.05,1.2)
                transform=compile_projection(azimuth_degrees=az,elevation_degrees=el,flip_x=flip)
                for point in ((0,0,0),(1,2,3),(-2,-1,9)):
                    projected=project_surface_position(point,transform=transform,width=w,depth=d,height=h,voxel_size=voxel,center_xy=centred)
                    reference=ProjectionAlignment(.1,-.05,1.2).source_uv(projected.u,projected.v)
                    for a,b in zip(frame.project(point),reference):self.assertAlmostEqual(a,b,places=11)

    def test_runtime_never_imports_engine_and_has_independent_manifest(self):
        for path in FOLDER.glob('*.py'):
            tree=ast.parse(path.read_text('utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom) and node.level==0:
                    self.assertFalse((node.module or '').split('.')[0] in {'core','implementations','operators','properties','blender_projection_tool'})
                if isinstance(node,ast.Import):
                    self.assertFalse(any(n.name.split('.')[0] in {'core','implementations','blender_projection_tool'} for n in node.names))
        manifest=tomllib.loads((FOLDER/'blender_manifest.toml').read_text('utf-8'))
        engine=tomllib.loads((ROOT/'blender_manifest.toml').read_text('utf-8'))
        self.assertNotEqual(manifest['id'],engine['id'])
        self.assertIn('/extensions/',engine['build']['paths_exclude_pattern'])
        self.assertNotIn('bpy',sys.modules)


if __name__=='__main__':unittest.main()
