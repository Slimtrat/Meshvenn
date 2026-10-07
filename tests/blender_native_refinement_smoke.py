"""Exercise the extension's INPUT/GEOMETRY path, UI property and cleanup."""
import importlib
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))


def main():
    package = importlib.import_module(ROOT.name)
    pipeline = importlib.import_module(f'{ROOT.name}.core.pipeline_contracts')
    input_module = importlib.import_module(f'{ROOT.name}.implementations.projection_images')
    geometry_module = importlib.import_module(f'{ROOT.name}.implementations.native_visual_hull')
    execution = importlib.import_module(f'{ROOT.name}.implementations.native_visual_hull.execution')
    from core.projection_frame import native_projection_frame, native_projection_axes
    from core.projection_math import compile_projection, project_normalized_point, NormalizedPoint
    package.register()
    try:
        settings = bpy.context.scene.bpt_settings
        assert settings.surface_refinement == 'none'
        settings.resolution = 32
        settings.normalize_height = True
        settings.target_height = 2
        settings.projections.clear()
        image = bpy.data.images.new('OrganicSmoke',width=32,height=32,alpha=True)
        image.pixels.foreach_set([v for y in range(32) for x in range(32)
                                  for v in (.3,.4,.5,1. if (x-15.5)**2+(y-15.5)**2 <= 12**2 else 0.)])
        for az in (0,math.pi/2):
            view = settings.projections.add()
            view.name = str(az)
            view.image = image
            view.azimuth = az
        context = pipeline.PipelineContext(scene=bpy.context.scene,settings=settings)
        prepared = input_module.ProjectionImagesImplementation().execute(context)
        assert prepared.success, prepared.message
        context.set_output(pipeline.PipelineStage.INPUT,prepared.payload)
        geometry = geometry_module.NativeVisualHullImplementation()
        faithful = geometry.execute(context)
        assert faithful.success, faithful.message
        settings.surface_refinement = 'organic'
        organic = geometry.execute(context)
        assert organic.success, organic.message
        output = organic.payload
        assert faithful.payload.native_mesh.indices == output.native_mesh.indices
        assert faithful.payload.native_mesh.vertices != output.native_mesh.vertices
        assert output.metadata['surface_refinement']['mode'] == 'organic'
        assert output.metadata['surface_refinement']['topology_preserved']
        finish = output.metadata['surface_refinement']
        assert finish['algorithm'] == 'contour-taubin-v2'
        assert finish['micro_finish']['algorithm'] == 'bounded-laplacian-v1'
        assert finish['micro_finish']['iterations'] == 6
        assert finish['micro_finish']['strength'] == .1
        assert finish['mean_contour_residual_after_in_voxels'] < finish['mean_contour_residual_before_in_voxels']
        assert finish['maximum_displacement_in_voxels'] <= .75
        assert abs(output.blender_object.dimensions.z-2) < 1e-6
        actual = tuple(c for vertex in output.blender_object.data.vertices for c in vertex.co)
        assert actual == tuple(output.native_mesh.vertices), 'Native/BVH and Blender coordinates differ'
        assert json.loads(output.blender_object['bpt_surface_refinement']) == output.metadata['surface_refinement']
        before = (set(bpy.data.objects.keys()),set(bpy.data.meshes.keys()))
        with patch.object(execution,'_write_geometry_metadata',side_effect=RuntimeError('Injected rollback')):
            try:
                geometry.execute(context)
            except RuntimeError as exc:
                assert str(exc) == 'Injected rollback'
            else:
                raise AssertionError('Expected injected failure')
        assert before == (set(bpy.data.objects.keys()),set(bpy.data.meshes.keys()))
        config_module = importlib.import_module(f'{ROOT.name}.implementations.native_visual_hull.config')
        from dataclasses import replace
        config = config_module._config_from_settings(settings)
        try:
            replace(config,mesh_mode='blocks').validate()
        except ValueError:
            pass
        else:
            raise AssertionError('Blocks plus organic must be rejected')
        # Check Blender's actual frame spans, including non-square pixels and
        # pole orientation; a camera roll error can silently erase entire arms.
        camera = bpy.data.cameras.new('ProjectionFrameSmoke')
        camera.type = 'ORTHO'
        scene = bpy.context.scene
        scene.render.resolution_x,scene.render.resolution_y = 148,164
        for az,el in ((0,0),(45,0),(0,90),(0,-90),(32,21)):
            camera.ortho_scale,scene.render.pixel_aspect_x = native_projection_frame(2,az,el,148,164)
            scene.render.pixel_aspect_y = 1
            frame = camera.view_frame(scene=scene)
            width = max(v.x for v in frame)-min(v.x for v in frame)
            height = max(v.y for v in frame)-min(v.y for v in frame)
            rotation = Matrix(native_projection_axes(az,el))
            point = (.6,-.3,.8)
            local = rotation @ Vector(point)
            expected = project_normalized_point(NormalizedPoint(*point),
                       compile_projection(azimuth_degrees=az,elevation_degrees=el))
            assert abs(.5+local.x/width-expected.u) < 1e-6
            assert abs(.5+local.y/height-expected.v) < 1e-6
        print('Native organic refinement, Blender coordinates, camera frames and rollback: PASS')
    finally:
        package.unregister()


if __name__ == '__main__':
    main()
