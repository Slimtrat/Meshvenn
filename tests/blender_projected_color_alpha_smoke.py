"""Real PNG border -> projected sampler -> UV Bake -> GLB -> shader evidence.

This qualifies coverage-aware color filtering, not anatomical texture recovery.
Also measures all opaque/transparent horizontal borders of the packed UAL1 views.
"""
from __future__ import annotations

from array import array
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'tmp/projected-color-alpha-probe'
EXPECTED, TOLERANCE = (.25, .50, .75), .004


def module(name):
    return importlib.import_module(f'{ROOT.name}.{name}')


def render(obj, name, *, scale=2, emit_base_color=True, file_format='PNG'):
    from scripts.render_turntable import setup_render, create_camera
    from scripts.render_material_projections import _emit_base_color
    if emit_base_color:
        _emit_base_color([obj])
    camera = create_camera(target=Vector(), model_size=Vector((2, 2, 0)))
    camera.location, camera.rotation_euler = (0, 0, 3), (0, 0, 0)
    camera.data.ortho_scale = scale
    setup_render(size=32, samples=1)
    scene = bpy.context.scene
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode, scene.render.image_settings.color_depth = 'RGBA', '16'
    scene.view_settings.view_transform, scene.view_settings.look = 'Standard', 'None'
    scene.view_settings.exposure, scene.view_settings.gamma = 0, 1
    scene.render.image_settings.file_format = file_format
    if file_format == 'OPEN_EXR':
        scene.render.image_settings.color_depth = '32'
    path = OUT / f"{name}{'.exr' if file_format == 'OPEN_EXR' else '.png'}"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path), check_existing=False)
    buffer = module('core.projected_material').ImageBuffer.from_blender_image(image)
    bpy.data.images.remove(image)
    bpy.data.objects.remove(camera, do_unlink=True)
    return buffer


def real_alpha_modes(projected):
    from scripts.render_turntable import clear_scene
    clear_scene()
    mesh = bpy.data.meshes.new('RealHalfCoverage')
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new('RealHalfCoverage', mesh)
    bpy.context.scene.collection.objects.link(obj)
    material = bpy.data.materials.new('RealHalfCoverageEmission')
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    output = next(node for node in nodes if node.type == 'OUTPUT_MATERIAL')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (*EXPECTED, 1)
    emission.inputs['Strength'].default_value = 1
    transparent, mix = nodes.new('ShaderNodeBsdfTransparent'), nodes.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = .5
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs['Surface'])
    mesh.materials.append(material)
    partial16 = render(obj, 'real-half-coverage-16', emit_base_color=False)
    assert partial16.alpha_mode == 'PREMUL' and partial16.source_alpha_mode == 'STRAIGHT'
    partial_exr = render(obj, 'real-half-coverage-linear', emit_base_color=False, file_format='OPEN_EXR')
    image = bpy.data.images.load(str(OUT / 'real-half-coverage-16.png'), check_existing=False)
    scene = bpy.context.scene
    scene.render.image_settings.file_format, scene.render.image_settings.color_depth = 'PNG', '8'
    image.save_render(filepath=str(OUT / 'real-half-coverage-8.png'), scene=scene)
    bpy.data.images.remove(image)
    image = bpy.data.images.load(str(OUT / 'real-half-coverage-8.png'), check_existing=False)
    partial8 = projected.ImageBuffer.from_blender_image(image)
    assert not image.is_float and partial8.rgb_encoding == 'sRGB' and partial8.alpha_mode == 'STRAIGHT'
    bpy.data.images.remove(image)
    records = []
    for name, buffer in (('PNG16', partial16), ('PNG8', partial8), ('EXR32', partial_exr)):
        color = buffer.sample_bilinear_alpha_aware(.5, .5)
        error = max(abs(actual - expected) for actual, expected in zip(color, (*EXPECTED, .5)))
        assert error < TOLERANCE, (name, color, error)
        records.append(dict(format=name, source_alpha_mode=buffer.source_alpha_mode,
                            buffer_alpha_mode=buffer.alpha_mode, rgb_encoding=buffer.rgb_encoding,
                            projected_linear_rgba=color, max_linear_error=error))
    # Non-Color explicitly treats file channel values as linear numeric data,
    # not the sRGB color above. For PNG16 Blender also leaves this RNA straight.
    image = bpy.data.images.load(str(OUT / 'real-half-coverage-16.png'), check_existing=False)
    image.colorspace_settings.name = 'Non-Color'
    image.reload()
    noncolor = projected.ImageBuffer.from_blender_image(image)
    assert noncolor.alpha_mode == 'STRAIGHT' and noncolor.rgb_encoding == 'scene-linear'
    expected_numeric = tuple(1.055 * value ** (1 / 2.4) - .055 for value in EXPECTED)
    numeric = noncolor.sample_bilinear_alpha_aware(.5, .5)
    error = max(abs(a - b) for a, b in zip(numeric, (*expected_numeric, .5)))
    assert error < .0001, (numeric, expected_numeric)
    records.append(dict(format='PNG16 Non-Color numeric data', projected_linear_rgba=numeric,
                        buffer_alpha_mode=noncolor.alpha_mode, rgb_encoding=noncolor.rgb_encoding,
                        max_linear_error=error))
    bpy.data.images.remove(image)
    clear_scene()
    return records


def packed_fixture_borders(projected):
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'example/v2/modular/UAL1/source.blend'))
    records = []
    for image in sorted((image for image in bpy.data.images if image.name.startswith('Appearance ')),
                        key=lambda image: image.name):
        buffer = projected.ImageBuffer.from_blender_image(image)
        count, old_max, new_max = 0, 0.0, 0.0
        for y in range(buffer.height):
            for x in range(buffer.width - 1):
                left, right = buffer.rgba(x, y), buffer.rgba(x + 1, y)
                if {left[3], right[3]} != {0.0, 1.0}:
                    continue
                expected = left if left[3] == 1 else right
                uv = ((x + .5) / (buffer.width - 1), y / (buffer.height - 1))
                old, new = buffer.sample_bilinear(*uv), buffer.sample_bilinear_alpha_aware(*uv)
                old_max = max(old_max, max(abs(a - b) for a, b in zip(old[:3], expected[:3])))
                new_max = max(new_max, max(abs(a - b) for a, b in zip(new[:3], expected[:3])))
                assert abs(new[3] - old[3]) < 1e-9
                count += 1
        assert count > 100 and old_max > .1 and new_max < 1e-6
        records.append(dict(name=image.name, alpha_mode=buffer.alpha_mode, border_samples=count,
                            legacy_max_linear_error=old_max, corrected_max_linear_error=new_max))
    assert len(records) == 10
    return records


def invalid_mode_boundaries(projected):
    """Packed channels survive INPUT; MATERIAL refuses before touching data."""
    from scripts.render_turntable import clear_scene
    clear_scene()
    mesh = bpy.data.meshes.new('InvalidCoverageProof')
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new('InvalidCoverageProof', mesh)
    bpy.context.scene.collection.objects.link(obj)
    uv = mesh.uv_layers.new(name='MeshvennUV')
    for loop in mesh.loops:
        uv.data[loop.index].uv = (.2 + loop.index * .1, .4)
    material = bpy.data.materials.new('KeepUserMaterial')
    mesh.materials.append(material)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    packed = projected.ImageBuffer(2, 2, array('f', (*EXPECTED, 1)) * 4, 'CHANNEL_PACKED')
    # INPUT/GEOMETRY-only and historical channel-wise reads remain legal.
    view = projected.ProjectedMaterialView.from_image_buffer(name='packed', image_buffer=packed,
                                                            azimuth_degrees=0, elevation_degrees=0)
    assert packed.sample_bilinear(.5, .5)[3] == 1
    frame = module('core.geometry_contracts').GeometryProjectionSpace(2, 2, 2)
    pipeline = module('core.pipeline_contracts')
    context = pipeline.PipelineContext(scene=bpy.context.scene)

    def snapshot():
        return (tuple((layer.name, tuple(tuple(point.uv) for point in layer.data))
                      for layer in mesh.uv_layers), tuple(mesh.materials),
                tuple(bpy.data.images), tuple(bpy.data.materials), tuple(mesh.color_attributes),
                bpy.context.view_layer.objects.active, tuple(bpy.context.selected_objects))

    before = snapshot()
    cases = [(packed, 'coverage alpha'),
             (projected.ImageBuffer(2, 2, array('f', (*EXPECTED, float('nan'))) * 4), 'coverage alpha'),
             (projected.ImageBuffer(2, 2, array('f', (*EXPECTED, 2)) * 4), 'coverage alpha'),
             (projected.ImageBuffer(2, 2, array('f', (float('nan'), .5, .75, 1)) * 4), 'covered RGB'),
             (projected.ImageBuffer(2, 2, array('f', EXPECTED)), 'buffer dimensions'),
             (projected.ImageBuffer(2, 2, array('f', (*EXPECTED, 1)) * 4,
                                    rgb_encoding='unsupported:Uncertified'), 'encoding is not certified')]
    for invalid, fragment in cases:
        view = projected.ProjectedMaterialView.from_image_buffer(name='invalid', image_buffer=invalid,
                                                                azimuth_degrees=0, elevation_degrees=0)
        surface = module('core.geometry_contracts').GeometrySurfaceOutput(
            obj, SimpleNamespace(material_views=(view,)), frame, 'invalid-coverage-proof')
        context.set_output(pipeline.PipelineStage.GEOMETRY, surface)
        uv_result = module('implementations.uv_bake').UVBakeImplementation().execute(context)
        assert not uv_result.success and fragment in uv_result.message, uv_result.message
        assert snapshot() == before
        legacy_result = module('implementations.projected_color').ProjectedColorImplementation().execute(context)
        assert not legacy_result.success and fragment in legacy_result.message, legacy_result.message
        assert snapshot() == before
        try:
            projected.apply_projected_material(obj, [view], volume_width=2, volume_depth=2, volume_height=2)
        except ValueError as error:
            assert fragment in str(error), str(error)
        else:
            raise AssertionError('Direct projected API accepted invalid color input.')
        assert snapshot() == before
    # Optional typed appearance is revalidated even if its arrays changed after
    # construction. The unchanged GEOMETRY input cannot conceal that mutation.
    valid = projected.ImageBuffer(2, 2, array('f', (*EXPECTED, 1)) * 4)
    mask = module('core.image_mask').BinaryMask(2, 2, bytes((1, 1, 1, 1)))
    base = projected.ProjectedMaterialView.from_image_buffer(name='front', image_buffer=valid,
                 azimuth_degrees=0, elevation_degrees=0, mask=mask)
    source = module('core.geometry_contracts').GeometrySurfaceOutput(
        obj, SimpleNamespace(material_views=(base,)), frame, 'valid-coverage-proof')
    appearance_buffer = projected.ImageBuffer(2, 2, array('f', (*EXPECTED, 1)) * 4)
    appearance_view = projected.ProjectedMaterialView.from_image_buffer(name='front', image_buffer=appearance_buffer,
                       azimuth_degrees=0, elevation_degrees=0, mask=mask)
    context.set_output(pipeline.PipelineStage.GEOMETRY, source)
    context.material_input = module('core.material_inputs').MaterialProjectionInput(
        (appearance_view,), frame, 'a' * 64, 'source-color-image')
    appearance_buffer.pixels[0] = float('nan')
    result = module('implementations.uv_bake').UVBakeImplementation().execute(context)
    assert not result.success and snapshot() == before
    context.material_input = None
    clear_scene()
    print('Invalid alpha/RGB/buffer/encoding: default UVBake, legacy stage and direct API reject before mutation PASS')


def main():
    from scripts.render_turntable import clear_scene
    OUT.mkdir(parents=True, exist_ok=True)
    projected = module('core.projected_material')
    alpha_formats = real_alpha_modes(projected)
    fixture = packed_fixture_borders(projected)
    invalid_mode_boundaries(projected)
    clear_scene()
    mesh = bpy.data.meshes.new('CoverageFilteringProof')
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new('CoverageFilteringProof', mesh)
    bpy.context.scene.collection.objects.link(obj)
    material = bpy.data.materials.new('KnownOpaqueBaseColor')
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value = (*EXPECTED, 1)
    mesh.materials.append(material)
    source = render(obj, 'source-with-transparent-background', scale=4)
    assert source.source_alpha_mode == 'STRAIGHT' and source.alpha_mode == 'PREMUL'
    x, y = next((x, y) for y in range(source.height) for x in range(source.width - 1)
                if source.rgba(x, y)[3] == 1 and source.rgba(x + 1, y)[3] == 0)
    opaque, empty = source.rgba(x, y), source.rgba(x + 1, y)
    # A two-pixel kernel copied from the actual PNG makes the precise border
    # position deterministic, without injecting the expected color into bake.
    border = projected.ImageBuffer(2, 2, array('f', (*opaque, *empty) * 2), source.alpha_mode,
                                   source.rgb_encoding, source.source_alpha_mode)
    view = projected.ProjectedMaterialView.from_image_buffer(name='real-png-border', image_buffer=border,
                                                            azimuth_degrees=0, elevation_degrees=0)
    blend = module('core.projected_material.blending')._blend_projected_color_detailed
    selected = blend((0, 0, 1), (0, -1, 0), [view], width=2, depth=2, height=2,
                     voxel_size=1, center_xy=True)
    assert not selected.used_fallback and selected.selected_samples == 1
    legacy = border.sample_bilinear(.5, .5)
    assert max(abs(a - b) for a, b in zip(legacy[:3], EXPECTED)) > .3
    assert selected.color[3] == 1
    bake = module('core.uv_bake')
    corners = [bake.UVBakeVertex(tuple(vertex.co), (0, 0, 1), uv) for vertex, uv in
               zip(mesh.vertices, ((0, 0), (1, 0), (1, 1), (0, 1)))]
    result = bake.bake_uv_texture([bake.UVBakeTriangle(*[corners[index] for index in indices])
                                  for indices in ((0, 1, 2), (0, 2, 3))],
            lambda position, normal: bake.SurfaceColorSample(selected.color,
                                 used_fallback=selected.used_fallback, selected_samples=selected.selected_samples),
            config=bake.UVBakeConfig(width=16, height=16, padding_pixels=0, samples_per_axis=2))
    assets = module('implementations.uv_bake.assets')
    image = assets._create_baked_image(obj, result)
    uv = mesh.uv_layers.new(name='ProofUV')
    for loop in mesh.loops:
        uv.data[loop.index].uv = corners[loop.vertex_index].uv
    baked_material = assets._create_baked_material(obj, image=image, uv_layer_name=uv.name)
    mesh.materials.clear()
    mesh.materials.append(baked_material)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    glb = OUT / 'coverage-filtered.glb'
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True)
    baked = render(obj, 'baked-shader')
    baked_rgb = baked.rgba(baked.width // 2, baked.height // 2)[:3]
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(glb))
    imported = next(item for item in bpy.context.scene.objects if item.type == 'MESH')
    imported_buffer = render(imported, 'reimported-shader')
    imported_rgb = imported_buffer.rgba(imported_buffer.width // 2, imported_buffer.height // 2)[:3]
    maximum = max(abs(a - b) for values in (opaque[:3], selected.color[:3], baked_rgb, imported_rgb)
                  for a, b in zip(values, EXPECTED))
    assert maximum <= TOLERANCE, (maximum, TOLERANCE)
    report = dict(passed=True, expected_linear_rgb=EXPECTED, source_alpha_mode=source.alpha_mode,
                  legacy_border_linear_rgb=legacy[:3], projected_border_linear_rgb=selected.color[:3],
                  filtered_confidence=border.sample_bilinear_alpha_aware(.5, .5)[3],
                  baked_shader_linear_rgb=baked_rgb, reimported_shader_linear_rgb=imported_rgb,
                  max_linear_error=maximum, tolerance=TOLERANCE, packed_fixture_border_probes=fixture,
                  real_partial_alpha_formats=alpha_formats,
                  scope='real PNG boundary filtering and portable opaque color transport; not full spatial texture recovery')
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', 'utf-8')
    print(json.dumps(report, indent=2))
    print('Projected color alpha-aware PNG/UV/GLB/shader smoke PASS')


if __name__ == '__main__':
    main()
