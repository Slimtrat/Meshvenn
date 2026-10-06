from array import array
from dataclasses import replace
import math
import unittest

from core.native_bridge.models import NativeMesh
from core.surface_refinement import refine_native_surface


def mesh(points, faces):
    starts, indices = [], []
    for face in faces:
        starts.append(len(indices))
        indices.extend(face)
    return NativeMesh(array('f', (x for p in points for x in p)), array('i', indices),
                      array('i', starts), array('i', map(len, faces)))


def octahedron(scale=1., offset=(0,0,0)):
    points = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    faces = [(0,2,4),(2,1,4),(1,3,4),(3,0,4),
             (2,0,5),(1,2,5),(3,1,5),(0,3,5)]
    return mesh([tuple(scale*p[k]+offset[k] for k in range(3)) for p in points], faces)


class SurfaceRefinementTests(unittest.TestCase):
    def test_none_preserves_identity_and_buffers(self):
        original = octahedron()
        result, report = refine_native_surface(original, voxel_size=1)
        self.assertIs(result, original)
        self.assertFalse(report['applied'])

    def test_closed_volume_topology_and_displacement_are_bounded(self):
        original = octahedron()
        saved = original.vertices.tolist()
        result, report = refine_native_surface(original, voxel_size=.2, mode='organic')
        self.assertEqual(original.vertices.tolist(), saved)
        self.assertIs(result.indices, original.indices)
        self.assertIs(result.polygon_starts, original.polygon_starts)
        self.assertEqual(report['volume_checked_component_count'], 1)
        self.assertLessEqual(report['maximum_component_volume_drift'], .02)
        self.assertLessEqual(report['maximum_displacement_in_voxels'], .75001)
        self.assertTrue(report['face_orientation_preserved'])
        self.assertTrue(report['applied'])

    def test_open_grid_pins_boundary_and_reduces_noise(self):
        size = 9
        points = [(x,y,.15*(-1)**(x+y)) for y in range(size) for x in range(size)]
        faces = [(y*size+x,y*size+x+1,(y+1)*size+x+1,(y+1)*size+x)
                 for y in range(size-1) for x in range(size-1)]
        original = mesh(points,faces)
        result, report = refine_native_surface(original, voxel_size=1, mode='organic')
        for i in range(size*size):
            if i%size in (0,size-1) or i//size in (0,size-1):
                self.assertEqual(result.vertices[i*3:i*3+3], original.vertices[i*3:i*3+3])
        self.assertLess(report['roughness_after_in_voxels'], report['roughness_before_in_voxels'])
        self.assertEqual(report['pinned_vertex_count'], 32)
        self.assertIsNone(report['maximum_component_volume_drift'])

    def test_components_have_independent_volume_checks(self):
        a, b = octahedron(), octahedron(.1,(4,0,0))
        original = mesh([tuple(a.vertices[i:i+3]) for i in range(0,18,3)] +
                        [tuple(b.vertices[i:i+3]) for i in range(0,18,3)],
                        [tuple(a.indices[i:i+3]) for i in range(0,24,3)] +
                        [tuple(j+6 for j in b.indices[i:i+3]) for i in range(0,24,3)])
        _, report = refine_native_surface(original, voxel_size=.3, mode='organic')
        self.assertEqual(report['component_count'], 2)
        self.assertEqual(report['volume_checked_component_count'], 2)
        self.assertLessEqual(report['maximum_component_volume_drift'], .02)

    def test_scale_translation_and_determinism(self):
        first, report = refine_native_surface(octahedron(), voxel_size=.2, mode='organic')
        repeated, _ = refine_native_surface(octahedron(), voxel_size=.2, mode='organic')
        self.assertEqual(first.vertices, repeated.vertices)
        shifted, _ = refine_native_surface(octahedron(2,(7,8,9)), voxel_size=.4, mode='organic')
        for i,x in enumerate(first.vertices):
            self.assertAlmostEqual(shifted.vertices[i], 2*x+(7,8,9)[i%3], places=5)

    def test_degenerate_and_nonmanifold_vertices_are_pinned(self):
        original = mesh([(0,0,0),(1,0,0),(2,0,0),(1,1,0),(1,-1,0)],
                        [(0,1,2),(0,1,3),(1,0,4)])
        result, report = refine_native_surface(original, voxel_size=1, mode='organic')
        self.assertEqual(result.vertices,original.vertices)
        self.assertEqual(report['pinned_vertex_count'],5)

    def test_invalid_inputs_are_rejected(self):
        original = octahedron()
        for options in ({'mode':'unknown'}, {'mode':'organic','mesh_mode':'blocks'},
                        {'voxel_size':0}, {'voxel_size':math.inf}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                refine_native_surface(original, **({'voxel_size':1}|options))
        for invalid in (replace(original, indices=array('i',[-1]*24)),
                        replace(original, vertices=array('f',[math.nan]*18)),
                        replace(original, polygon_starts=array('i',[9]*8)),
                        replace(original, indices=array('i',list(original.indices)+[0]))):
            with self.assertRaises(ValueError):
                refine_native_surface(invalid, voxel_size=1, mode='organic')
