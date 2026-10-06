"""Prove Blender's lossy custom-normal representation without relaxing glTF data.

The importer feeds float32 vectors into Mesh.normals_split_custom_set_from_vertices.
Blender encodes those vectors relative to each local smooth fan. Cutting regions
or a tiny bind-matrix roundoff can change that encoding: its decoded values are
not an appropriate oracle for the authoritative NORMAL accessor. Capture the
input at the recognized importer boundary, independently validate it, and replay
the public Mesh API on an isolated copy to certify the actual representation.
"""

from __future__ import annotations

from contextlib import contextmanager
import importlib
import inspect
import math

import bpy
from mathutils import Vector


CODEC_TOLERANCE = 2.0e-6
_capture_in_progress = False


@contextmanager
def capture_import_normal_inputs():
    """Instrument only the synchronous verification import; always restore it."""
    global _capture_in_progress
    importer = importlib.import_module("io_scene_gltf2.blender.imp.mesh")
    original = getattr(importer, "set_poly_smoothing", None)
    signature = ("gltf", "pymesh", "mesh", "vert_normals", "loop_vidxs")
    if not callable(original) or tuple(inspect.signature(original).parameters) != signature:
        raise ValueError("Unsupported Blender glTF normal-codec interface; modular verification cannot certify this importer.")
    if _capture_in_progress:
        raise ValueError("Nested Blender glTF normal-codec verification is unsupported.")
    captured = {}

    def record(gltf, pymesh, mesh, vert_normals, loop_vidxs):
        if gltf.import_settings.get("merge_vertices") or gltf.import_settings.get("import_shading") != "NORMALS":
            raise ValueError("Modular verification requires unmerged glTF vertices and authored normals.")
        vectors = tuple(tuple(float(value) for value in row) for row in vert_normals)
        if len(vectors) != len(mesh.vertices) or any(len(row) != 3 or any(
                not math.isfinite(value) for value in row) for row in vectors):
            raise ValueError("Blender importer changed the pre-codec vertex-normal inventory.")
        if any(abs(sum(value * value for value in row) - 1) > CODEC_TOLERANCE for row in vectors):
            raise ValueError("Blender importer produced non-unit pre-codec vertex normals.")
        pointer = mesh.as_pointer()
        if pointer in captured:
            raise ValueError("Blender importer reused a mesh at the normal-codec boundary.")
        captured[pointer] = vectors
        return original(gltf, pymesh, mesh, vert_normals, loop_vidxs)

    _capture_in_progress = True
    importer.set_poly_smoothing = record
    try:
        yield captured
    finally:
        importer.set_poly_smoothing = original
        _capture_in_progress = False


def verify_imported_normal_codec(obj, captured):
    """Return independent pre-codec corner normals and exact replay metrics.

    This never changes the imported object or its mesh. The caller must compare
    returned inputs against the source normals after the strict raw GLB proof.
    """
    mesh = obj.data
    vectors = captured.get(mesh.as_pointer())
    if vectors is None or len(vectors) != len(mesh.vertices):
        raise ValueError("Blender importer did not expose this region's recognized normal-codec inputs.")
    clone = mesh.copy()
    try:
        clone.normals_split_custom_set_from_vertices(vectors)
        if len(clone.corner_normals) != len(mesh.corner_normals):
            raise ValueError("Blender normal-codec replay changed the corner inventory.")
        codec_error = max((max(abs(a - b) for a, b in zip(original.vector, reproduced.vector))
                           for original, reproduced in zip(mesh.corner_normals, clone.corner_normals)), default=0.0)
        if codec_error > CODEC_TOLERANCE:
            raise ValueError(f"Blender imported normals do not reproduce its verified codec inputs ({codec_error:.6g}).")
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        input_normals = tuple((normal_matrix @ Vector(vectors[loop.vertex_index])).normalized()
                              for loop in mesh.loops)
        output_normals = tuple((normal_matrix @ normal.vector).normalized() for normal in mesh.corner_normals)
        quantization_error = max((max(abs(a - b) for a, b in zip(before, after))
                                  for before, after in zip(input_normals, output_normals)), default=0.0)
        quantization_angle = max((math.atan2(before.cross(after).length, before.dot(after))
                                  for before, after in zip(input_normals, output_normals)), default=0.0)
        mesh.calc_loop_triangles()
        return {"_pre_codec_corner_normals": tuple(tuple(input_normals[loop])
                                                 for triangle in mesh.loop_triangles for loop in triangle.loops),
                "max_imported_normal_codec_error": codec_error,
                "max_imported_normal_quantization_error": quantization_error,
                "max_imported_normal_quantization_angle_radians": quantization_angle}
    finally:
        bpy.data.meshes.remove(clone)


__all__ = ("CODEC_TOLERANCE", "capture_import_normal_inputs", "verify_imported_normal_codec")
