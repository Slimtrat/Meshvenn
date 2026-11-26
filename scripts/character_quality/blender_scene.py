"""Blender-only source rays, exact GLB reloads and common presentation frames."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import zlib


def record(path,root):
    data=Path(path).read_bytes()
    return dict(path=Path(path).relative_to(root).as_posix(),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))


def png_mask(path,size,values):
    def chunk(kind,data):return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    rows=b"".join(b"\0"+bytes(c for x in range(size) for c in (255,255,255,255*values[y*size+x])) for y in reversed(range(size)))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",size,size,8,6,0,0,0))+
        chunk(b"IDAT",zlib.compress(rows,9))+chunk(b"IEND",b""))


def load(path):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert not bpy.context.scene.objects
    before=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    bpy.ops.import_scene.gltf(filepath=str(Path(path).resolve()))
    objects=tuple(o for o in bpy.context.scene.objects if o.type=="MESH")
    if not objects:raise ValueError("GLB has no real mesh geometry.")
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=before:raise ValueError("GLB input changed during reload.")
    return objects


def inventory(objects):
    import bpy
    points=[];triangles=[]
    depsgraph=bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        evaluated=obj.evaluated_get(depsgraph)
        mesh=evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            offset=len(points)
            points.extend(tuple(evaluated.matrix_world@v.co) for v in mesh.vertices)
            triangles.extend(tuple(offset+i for i in t.vertices) for t in mesh.loop_triangles)
        finally:evaluated.to_mesh_clear()
    bounds=[[min(p[a] for p in points) for a in range(3)],[max(p[a] for p in points) for a in range(3)]]
    return dict(mesh_objects=len(objects),vertices=len(points),triangles=len(triangles),bounds=bounds,
        mesh_names=sorted(o.name for o in objects)),points,triangles


def ray_masks(objects,output,size,angles):
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Matrix,Vector
    from mathutils.bvhtree import BVHTree
    from core.image_mask import BinaryMask
    from core.projection_frame import native_projection_axes,native_projection_frame
    from core.projection_math import compile_projection,project_normalized_point,NormalizedPoint
    info,points,triangles=inventory(objects)
    tree=BVHTree.FromPolygons(points,triangles,all_triangles=True)
    result=[]
    for name,azimuth,elevation in angles:
        right,up,direction=native_projection_axes(azimuth,elevation)
        transform=compile_projection(azimuth_degrees=azimuth,elevation_degrees=elevation)
        data=bpy.data.cameras.new(name);data.type="ORTHO"
        cam=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(cam)
        cam.location=Vector(direction)*6
        cam.rotation_euler=Matrix((right,up,direction)).transposed().to_euler()
        scene=bpy.context.scene;scene.camera=cam
        scene.render.resolution_x=scene.render.resolution_y=size;scene.render.resolution_percentage=100
        data.ortho_scale,scene.render.pixel_aspect_x=native_projection_frame(2.,azimuth,elevation,size,size)
        scene.render.pixel_aspect_y=1.
        bpy.context.view_layer.update()
        maximum=0.
        for point in ((.3,-.2,.7),(-.4,.5,-.6),(0,0,0)):
            actual=world_to_camera_view(scene,cam,Vector(point))
            expected=project_normalized_point(NormalizedPoint(*point),transform)
            maximum=max(maximum,abs(actual.x-expected.u),abs(actual.y-expected.v))
        if maximum>2e-6:raise ValueError("Blender/native source camera frames disagree.")
        # Exact source triangles only produce inputs; no source surface is used
        # by reconstruction or by the bounded production contour refinement.
        values=bytearray(size*size)
        backwards=Vector(direction);ray=-backwards
        r,u=Vector(right),Vector(up)
        for y in range(size):
            vertical=(2*(y+.5)/size-1)*transform.vertical_extent
            base=u*vertical+backwards*4
            for x in range(size):
                horizontal=(2*(x+.5)/size-1)*transform.horizontal_extent
                values[y*size+x]=int(tree.ray_cast(base+r*horizontal,ray,8.)[0] is not None)
        mask=BinaryMask(size,size,bytes(values))
        path=output/(name+".png");png_mask(path,size,values)
        result.append(dict(id=name,azimuth_degrees=azimuth,elevation_degrees=elevation,flip_x=False,
            width=size,height=size,physical_cube_side=2.,ortho_scale=data.ortho_scale,pixel_aspect_x=scene.render.pixel_aspect_x,
            maximum_native_uv_error=maximum,sampling="pixel-centres; <=0.5 pixel native endpoint nearest quantization",
            png=record(path,output.parent),foreground_pixels=mask.occupied_count,mask=mask))
    return result,info


def neutral(objects):
    import bpy
    material=bpy.data.materials.new("common_neutral_comparison")
    material.use_nodes=True
    shader=material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value=(.43,.49,.53,1.)
    shader.inputs["Roughness"].default_value=.65
    shader.inputs["Metallic"].default_value=0.
    for obj in objects:
        obj.data.materials.clear();obj.data.materials.append(material)
        for polygon in obj.data.polygons:polygon.use_smooth=True


def hero(path,output,size):
    import bpy
    from mathutils import Matrix,Vector
    from core.projection_frame import native_projection_axes
    objects=load(path);neutral(objects)
    scene=bpy.context.scene
    scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=16
    scene.cycles.seed=17;scene.cycles.use_denoising=True
    scene.cycles.use_adaptive_sampling=False;scene.cycles.max_bounces=2
    scene.render.threads_mode="FIXED";scene.render.threads=8
    scene.render.resolution_x=scene.render.resolution_y=size;scene.render.resolution_percentage=100
    scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1.
    scene.render.image_settings.file_format="PNG";scene.render.image_settings.color_mode="RGBA"
    scene.render.film_transparent=False
    scene.view_settings.view_transform="AgX";scene.view_settings.exposure=0
    world=bpy.data.worlds.new("common_world");world.use_nodes=True
    world.node_tree.nodes["Background"].inputs["Color"].default_value=(1,1,1,1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value=.45;scene.world=world
    for name,position,energy in (("key",(-3,-4,5),650),("fill",(4,-2,2),350),("rim",(0,3,4),500)):
        data=bpy.data.lights.new(name,"AREA");data.energy=energy;data.size=4
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=position
        obj.rotation_euler=(-obj.location).to_track_quat("-Z","Y").to_euler()
    axes=native_projection_axes(45.,-15.)
    data=bpy.data.cameras.new("common_hero");data.type="ORTHO";data.ortho_scale=2.5
    camera=bpy.data.objects.new("common_hero",data);scene.collection.objects.link(camera)
    camera.location=Vector(axes[2])*6;camera.rotation_euler=Matrix(axes).transposed().to_euler();scene.camera=camera
    scene.render.filepath=str(output.resolve());bpy.ops.render.render(write_still=True)


def export_and_reload(obj,path):
    import bpy
    bpy.context.view_layer.update()
    before=inventory((obj,))[0]
    bpy.ops.object.select_all(action="DESELECT");obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.export_scene.gltf(filepath=str(path.resolve()),export_format="GLB",use_selection=True,
        export_animations=False,export_cameras=False,export_lights=False,export_extras=True)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    objects=load(path);after=inventory(objects)[0]
    error=max(abs(a-b) for aa,bb in zip(before["bounds"],after["bounds"]) for a,b in zip(aa,bb))
    if before["triangles"]!=after["triangles"] or error>3e-6:raise ValueError("Export/reload changed the actual reconstruction geometry.")
    return dict(source_glb_sha256=digest,verified=True,reloaded_in_empty_scene=True,
        maximum_bounds_error=error,**after)
