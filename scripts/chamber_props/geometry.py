"""Closed, bevelled components with explicit pivots and ordinary UV coordinates."""
import math
import random
import bpy
from mathutils import Vector


def empty(name, parent=None, location=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = .05
    return obj


def finish(obj, parent, mat, bevel=0, seed=0):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new('Worn arris', 'BEVEL')
        modifier.width = bevel
        modifier.segments = 1
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    uv = obj.data.uv_layers.new(name='UVMap') if not obj.data.uv_layers else obj.data.uv_layers[0]
    rng = random.Random(seed)
    offsets = (rng.random(), rng.random())
    for face in obj.data.polygons:
        n = face.normal
        axes = (0, 2) if abs(n.y) >= max(abs(n.x), abs(n.z)) else ((1, 2) if abs(n.x) > abs(n.z) else (0, 1))
        for index in face.loop_indices:
            p = obj.data.vertices[obj.data.loops[index].vertex_index].co
            uv.data[index].uv = (p[axes[0]] * 3 + offsets[0], p[axes[1]] * 3 + offsets[1])
    # Design functions use root/world coordinates; retain those while parenting.
    matrix = obj.matrix_world.copy()
    obj.parent = parent
    bpy.context.view_layer.update()
    obj.matrix_world = matrix
    return obj


def box(name, center, size, parent, mat, bevel=.008, seed=0, chip=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if chip:
        rng = random.Random(seed)
        for vertex in obj.data.vertices:
            # Inward wear only: bounds never exceed the delivery contract.
            vertex.co.x *= 1 - rng.random() * chip
            vertex.co.z *= 1 - rng.random() * chip
    return finish(obj, parent, mat, bevel, seed)


def prism(name, polygon, front, back, parent, mat, bevel=.005, seed=0):
    count = len(polygon)
    verts = [(x, y, z) for y in (front, back) for x, z in polygon]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2*count))]
    faces += [(i, (i+1) % count, (i+1) % count + count, i+count) for i in range(count)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    # Recalculate orientation independent of input polygon winding.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    return finish(obj, parent, mat, bevel, seed)


def stud(name, center, radius, depth, parent, mat, axis='Y'):
    rotation = (math.pi/2, 0, 0) if axis == 'Y' else (0, math.pi/2, 0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=radius, depth=depth, location=center, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    return finish(obj, parent, mat, .003)


def ring(name, center, radius, tube, parent, mat):
    bpy.ops.mesh.primitive_torus_add(major_segments=16, minor_segments=4, location=center,
                                   major_radius=radius, minor_radius=tube, rotation=(math.pi/2, 0, 0))
    obj = bpy.context.object
    obj.name = name
    return finish(obj, parent, mat)


def merge_children(parent):
    """One mesh per semantic group, with at most three material surfaces."""
    meshes = [obj for obj in parent.children if obj.type == 'MESH']
    if not meshes:
        return
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    meshes[0].name = parent.name + 'Surface'
    # Keep flat facets and bevels; no fragile custom split normal extension.
    return meshes[0]
