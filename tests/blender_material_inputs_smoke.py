"""Real Blender evidence for calibrated color, alpha rejection and visibility."""
from __future__ import annotations
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
from dataclasses import replace

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))


def module(name):
    return importlib.import_module(f"{ROOT.name}.{name}")


def expect_error(callback, fragment):
    try:
        callback()
    except (ValueError, TypeError) as error:
        if fragment not in str(error):
            raise AssertionError(str(error)) from error
    else:
        raise AssertionError(f"Expected fail-closed rejection: {fragment}")


def check_visibility():
    visibility = module("core.material_visibility")
    # Real organic fixture, not a planar stand-in. Source ownership identifies
    # its hidden authoritative original, never a displayed partition copy.
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / "example/v2/modular/UAL1/source.blend"))
    source = next(obj for obj in bpy.data.objects if obj.type == "MESH" and
                  "meshvenn_modular_motion_catalogue" in obj)
    mesh = source.data
    mesh.calc_loop_triangles()
    old = visibility.MeshVisibilityTester.from_blender_object(source)
    exact = visibility.MeshVisibilityTester.from_blender_object(source, use_loop_triangles=True)
    mismatches = samples = 0
    for triangle in mesh.loop_triangles:
        points = [mesh.vertices[index].co for index in triangle.vertices]
        point = sum(points, Vector()) / 3
        direction = (points[1] - points[0]).cross(points[2] - points[0]).normalized()
        if direction.length == 0:
            continue
        old_clear, exact_clear = old.is_visible(tuple(point), tuple(direction)), exact.is_visible(tuple(point), tuple(direction))
        samples += 1
        mismatches += not old_clear and exact_clear
        if not exact_clear:
            # Neighbouring surfaces really can occlude the outward normal in
            # concave folds. This is not a reason to turn visibility off.
            continue
    if mismatches < 10:
        raise AssertionError(f"Nonplanar triangulation regression not exercised: {mismatches}/{samples}")
    # A true separate blocker remains blocked with exact triangles.
    blocker = bpy.data.meshes.new("OcclusionProof")
    blocker.from_pydata([(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new("OcclusionProof", blocker)
    bpy.context.scene.collection.objects.link(obj)
    tester = visibility.MeshVisibilityTester.from_blender_object(obj, use_loop_triangles=True)
    if tester.is_visible((0, 0, 0), (0, 0, 1)):
        raise AssertionError("True occlusion must remain blocked.")
    print(f"Exact loop-triangle visibility: {mismatches}/{samples} false self-occlusions removed; true occlusion preserved")
    projected = module("core.projected_material")
    frame_api = module("core.geometry_contracts")
    from array import array
    image = projected.ImageBuffer(2, 2, array("f", [.25, .5, .75, 1]) * 4)
    mask = module("core.image_mask").BinaryMask(2, 2, bytes([1]) * 4)
    views = tuple(projected.ProjectedMaterialView.from_image_buffer(name=str(angle), image_buffer=image,
                  azimuth_degrees=angle, elevation_degrees=0, mask=mask) for angle in (0, 90, 180, 270))
    geometry = frame_api.GeometrySurfaceOutput(source, SimpleNamespace(material_views=views),
                                               frame_api.GeometryProjectionSpace(64, 64, 64), "native-visual-hull")
    config = module("implementations.uv_bake.config").UVBakeMaterialConfig()
    sampler_api = module("implementations.uv_bake.sampler")
    normal = sampler_api._build_surface_sampler(geometry, config)
    detailed = sampler_api._build_surface_sampler(geometry, config, views=views, diagnostics=True)
    for triangle in tuple(mesh.loop_triangles)[::200]:
        point = sum((mesh.vertices[index].co for index in triangle.vertices), Vector()) / 3
        direction = triangle.normal
        a, b = normal(tuple(point), tuple(direction)), detailed(tuple(point), tuple(direction))
        assert a.color == b.color and a.selected_samples == b.selected_samples and a.used_fallback == b.used_fallback
    context_api = module("core.pipeline_contracts")
    context = context_api.PipelineContext()
    resolver = module("implementations.uv_bake.settings")._material_views_from_context
    assert resolver(context, geometry) is views
    context.material_input = {"views": views}
    expect_error(lambda: resolver(context, geometry), "MaterialProjectionInput")
    blank = replace(views[0], mask=module("core.image_mask").BinaryMask(2, 2, bytes(4)))
    refused = sampler_api._build_surface_sampler(geometry, config, views=(blank,), diagnostics=True)
    result = refused((0, 0, 32), (0, -1, 0))
    assert result.selected_samples == 0 and result.used_fallback
    assert refused.diagnostics["neutral_fallback_samples"] == 1
    assert refused.diagnostics["source_rejected_samples"] == 1
    alpha_zero = replace(views[0], image=projected.ImageBuffer(2, 2, array("f", [.25, .5, .75, 0]) * 4))
    sample_source = module("core.projected_material.sampling")._sample_source_view
    assert sample_source((0, 0, 32), (0, -1, 0), alpha_zero, **geometry.projection_space.as_projection_kwargs()) is None
    print("Legacy/default and detailed sampler outputs identical; absent input unchanged; alpha/mask reject without fake color")


def check_material_boundary():
    source_module = importlib.import_module("scripts.render_material_projections")
    material = bpy.data.materials.new("OpaqueProof")
    material.use_nodes = True
    mesh = bpy.data.meshes.new("ColorProof")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.materials.append(material)
    obj = bpy.data.objects.new("ColorProof", mesh)
    bpy.context.scene.collection.objects.link(obj)
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Alpha"].default_value = .5
    before = len(material.node_tree.nodes)
    expect_error(lambda: source_module._emit_base_color([obj]), "opaque")
    assert len(material.node_tree.nodes) == before
    shader.inputs["Alpha"].default_value = 1
    value = material.node_tree.nodes.new("ShaderNodeValue")
    material.node_tree.links.new(value.outputs[0], shader.inputs["Alpha"])
    expect_error(lambda: source_module._emit_base_color([obj]), "opaque")
    material.node_tree.links.remove(shader.inputs["Alpha"].links[0])
    output = next(node for node in material.node_tree.nodes if node.type == "OUTPUT_MATERIAL")
    mixed = material.node_tree.nodes.new("ShaderNodeMixShader")
    material.node_tree.links.new(mixed.outputs[0], output.inputs["Surface"])
    expect_error(lambda: source_module._emit_base_color([obj]), "Principled")
    material.node_tree.links.new(shader.outputs[0], output.inputs["Surface"])
    source_module._emit_base_color([obj])
    assert output.inputs["Surface"].links[0].from_node.type == "EMISSION"


if __name__ == "__main__":
    check_visibility()
    check_material_boundary()
    print("Material input / base-color / visibility smoke PASS")
