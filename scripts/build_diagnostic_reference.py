"""Author an original GPL robot and render a frozen pre-provider reference.

Run with Blender --background --factory-startup --python-exit-code 1 --python
scripts/build_diagnostic_reference.py -- [--output DIR] [--verify-glb-only].
No external asset, image provider, learned model or production character is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import zlib

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector, kdtree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.diagnostics_preflight import RasterInput

SCHEMA=1
BADGE_HEALTHY=(.025,.11,.80,1.)
BADGE_DEFECT=(.80,.025,.16,1.)
BADGE="badge_color"


def sha(data):return hashlib.sha256(data).hexdigest()


def write_json(path,value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")


def png(path,width,height,rgba):
    def chunk(kind,data):return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    rows=b"".join(b"\0"+bytes(rgba[4*y*width:4*(y+1)*width]) for y in reversed(range(height)))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,6,0,0,0))+
                     chunk(b"IDAT",zlib.compress(rows,9))+chunk(b"IEND",b""))


def material(name,color,metallic=0.):
    result=bpy.data.materials.new(name)
    result.use_nodes=True
    shader=result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value=color
    shader.inputs["Roughness"].default_value=.48
    shader.inputs["Metallic"].default_value=metallic
    return result


def build_robot():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials={name:material(name,color,metal) for name,color,metal in (
        ("shell_teal",(.055,.36,.30,1.),.1),("joint_slate",(.10,.15,.18,1.),.25),
        ("face_ivory",(.82,.75,.59,1.),.05),("visor_navy",(.018,.045,.075,1.),.15),
        ("eye_ice",(.70,.92,1.,1.),.05),("badge_cobalt",BADGE_HEALTHY,.05),
        ("trim_brass",(.72,.39,.10,1.),.3),("flag_coral",(.83,.20,.075,1.),.05))}
    recipe=[]
    def sphere(name,center,scale,paint,tilt=0.):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,radius=1.,location=center)
        obj=bpy.context.object
        obj.name=name
        obj.scale=scale
        obj.rotation_euler[1]=math.radians(tilt)
        obj.data.materials.append(materials[paint])
        for face in obj.data.polygons:face.use_smooth=True
        obj["authoring_origin"]="Meshvenn original mathematical primitive; GPL-3.0-or-later"
        recipe.append(dict(name=name,primitive="uv_sphere",segments=32,rings=16,center=center,scale=scale,
                           tilt_y_degrees=tilt,material=paint))
        return obj
    def cylinder(name,center,radius,depth,paint):
        bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=radius,depth=depth,location=center)
        obj=bpy.context.object
        obj.name=name
        obj.data.materials.append(materials[paint])
        for face in obj.data.polygons:face.use_smooth=len(face.vertices)==4
        recipe.append(dict(name=name,primitive="cylinder",vertices=24,center=center,radius=radius,depth=depth,material=paint))
    sphere("body",(0.,0.,-.08),(.31,.215,.39),"shell_teal")
    cylinder("neck",(0.,0.,.30),.10,.12,"joint_slate")
    sphere("head",(0.,0.,.55),(.29,.225,.25),"face_ivory")
    sphere("visor",(0.,-.205,.575),(.222,.055,.112),"visor_navy")
    for x,name in ((-.082,"left"),(.082,"right")):
        sphere("eye_"+name,(x,-.258,.60),(.026,.014,.033),"eye_ice")
    sphere("mouth",(0.,-.256,.525),(.055,.009,.012),"eye_ice")
    cylinder("antenna_stem",(-.10,0.,.82),.012,.18,"joint_slate")
    sphere("antenna_tip",(-.10,0.,.91),(.036,.036,.036),"flag_coral")
    sphere("badge_brass_ring",(-.10,-.217,-.005),(.116,.03,.109),"trim_brass")
    sphere(BADGE,(-.10,-.249,-.005),(.095,.016,.088),"badge_cobalt")
    for sign,side in ((-1,"left"),(1,"right")):
        sphere(side+"_shoulder",(sign*.315,0.,.145),(.092,.095,.10),"joint_slate")
        sphere(side+"_arm",(sign*.395,0.,-.005),(.074,.082,.18),"shell_teal",-sign*14)
        sphere(side+"_elbow",(sign*.438,0.,-.165),(.073,.078,.072),"joint_slate")
        sphere(side+"_hand",(sign*.475,-.01,-.255),(.090,.092,.092),"face_ivory")
        sphere(side+"_hip",(sign*.13,0.,-.44),(.087,.087,.08),"joint_slate")
        sphere(side+"_thigh",(sign*.13,0.,-.565),(.077,.082,.13),"shell_teal")
        sphere(side+"_knee",(sign*.13,-.01,-.69),(.076,.082,.071),"joint_slate")
        sphere(side+"_shin",(sign*.13,0.,-.785),(.071,.078,.105),"shell_teal")
        sphere(side+"_boot",(sign*.13,-.045,-.89),(.112,.145,.061),"joint_slate")
    cylinder("right_flag_pole",(.515,-.035,.235),.012,.98,"trim_brass")
    vertices=[(.53,-.045,.72),(.85,-.045,.65),(.53,-.045,.51),
              (.53,-.015,.72),(.85,-.015,.65),(.53,-.015,.51)]
    faces=[(0,2,1),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)]
    mesh=bpy.data.meshes.new("one_sided_flag_mesh")
    mesh.from_pydata(vertices,[],faces)
    obj=bpy.data.objects.new("right_flag_only",mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(materials["flag_coral"])
    recipe.append(dict(name=obj.name,primitive="authored_triangular_prism",vertices=vertices,faces=faces,material="flag_coral"))
    bpy.context.view_layer.update()
    return recipe


def geometry():
    result={}
    for obj in sorted((o for o in bpy.context.scene.objects if o.type=="MESH"),key=lambda o:o.name):
        mesh=obj.data
        mesh.calc_loop_triangles()
        points=[tuple(obj.matrix_world@v.co) for v in mesh.vertices]
        triangles=[tuple(tuple(round(c,7) for c in points[i]) for i in t.vertices) for t in mesh.loop_triangles]
        centroids=[tuple(sum(points[i][axis] for i in t.vertices)/3 for axis in range(3)) for t in mesh.loop_triangles]
        parent=list(range(len(points)))
        def find(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        welded={}
        for i,p in enumerate(points):
            key=tuple(round(c,6) for c in p)
            if key in welded:parent[find(i)]=find(welded[key])
            else:welded[key]=i
        for t in mesh.loop_triangles:
            for i in t.vertices[1:]:parent[find(i)]=find(t.vertices[0])
        result[obj.name]=dict(vertices=len(points),triangles=len(triangles),geometric_components=len({find(i) for i in range(len(points))}),
            minimum=[min(p[a] for p in points) for a in range(3)],maximum=[max(p[a] for p in points) for a in range(3)],
            triangle_position_sha256=sha(json.dumps(sorted(triangles),separators=(",",":")).encode()),points=points,centroids=centroids)
    return result


def reload_glb(path,expected):
    before=sha(path.read_bytes())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert not bpy.context.scene.objects
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    loaded=geometry()
    assert set(loaded)==set(expected),"A GLB part was lost or renamed."
    maximum=0.
    for name,original in expected.items():
        actual=loaded[name]
        assert actual["triangles"]==original["triangles"]
        assert actual["geometric_components"]==original["geometric_components"]
        for kind in ("points","centroids"):
            for source,target in ((original,actual),(actual,original)):
                tree=kdtree.KDTree(len(target[kind]))
                for i,p in enumerate(target[kind]):tree.insert(p,i)
                tree.balance()
                maximum=max(maximum,max(tree.find(p)[2] for p in source[kind]))
        for kind in ("minimum","maximum"):
            maximum=max(maximum,max(abs(a-b) for a,b in zip(actual[kind],original[kind])))
    assert maximum<2e-6,maximum
    assert sha(path.read_bytes())==before
    return dict(schema_version=1,source_glb_sha256=before,reloaded_in_empty_scene=True,mesh_objects=len(loaded),
        triangles=sum(o["triangles"] for o in loaded.values()),geometric_components=sum(o["geometric_components"] for o in loaded.values()),
        maximum_world_position_error=maximum,tolerance=2e-6,
        comparison="Symmetric world-vertex and triangle-centroid nearest distances, bounds, triangle and welded-component counts.",
        before={k:{a:b for a,b in v.items() if a not in ("points","centroids")} for k,v in expected.items()},
        after={k:{a:b for a,b in v.items() if a not in ("points","centroids")} for k,v in loaded.items()})


def stage():
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=32
    scene.cycles.seed=17
    scene.cycles.use_denoising=False
    scene.cycles.use_adaptive_sampling=False
    scene.cycles.max_bounces=1
    scene.cycles.diffuse_bounces=0
    scene.cycles.glossy_bounces=0
    scene.render.threads_mode="FIXED"
    scene.render.threads=8
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGBA"
    scene.render.image_settings.color_depth="8"
    scene.render.film_transparent=True
    scene.view_settings.view_transform="Standard"
    scene.view_settings.look="None"
    scene.view_settings.exposure=-.65
    scene.view_settings.gamma=1
    world=bpy.data.worlds.new("neutral_studio")
    world.use_nodes=True
    world.node_tree.nodes["Background"].inputs["Color"].default_value=(.8,.8,.8,1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value=.45
    scene.world=world
    for name,position,energy,size in (("key",(-3,-4,5),650,4),("fill",(4,-2,2),350,3),("rim",(0,3,4),500,3)):
        light=bpy.data.lights.new(name,"AREA")
        light.energy,light.shape,light.size=energy,"DISK",size
        obj=bpy.data.objects.new(name,light)
        scene.collection.objects.link(obj)
        obj.location=position
        obj.rotation_euler=(-obj.location).to_track_quat("-Z","Y").to_euler()


def camera(azimuth,size):
    scene=bpy.context.scene
    data=bpy.data.cameras.new("verified_cardinal")
    data.type="ORTHO"
    data.ortho_scale=2.
    data.clip_start,data.clip_end=.01,100.
    obj=bpy.data.objects.new("verified_cardinal",data)
    scene.collection.objects.link(obj)
    angle=math.radians(azimuth)
    obj.location=(6*math.sin(angle),-6*math.cos(angle),0)
    obj.rotation_euler=(-obj.location).to_track_quat("-Z","Y").to_euler()
    scene.camera=obj
    scene.render.resolution_x=scene.render.resolution_y=size
    scene.render.resolution_percentage=100
    scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
    bpy.context.view_layer.update()
    maximum=0.
    for point in ((.23,-.31,.47),(-.42,.27,-.61),(0,0,0)):
        uv=world_to_camera_view(scene,obj,Vector(point))
        expected=((point[0]*math.cos(angle)+point[1]*math.sin(angle)+1)/2,(point[2]+1)/2)
        maximum=max(maximum,abs(uv.x-expected[0]),abs(uv.y-expected[1]))
    assert maximum<2e-6,maximum
    return dict(projection="orthographic",azimuth_degrees=azimuth,elevation_degrees=0.,flip_x=False,
        ortho_scale=2.,width=size,height=size,alignment=dict(offset_u=0.,offset_v=0.,scale=1.),
        location=list(obj.location),rotation_euler=list(obj.rotation_euler),maximum_native_uv_error=maximum,
        pixel_convention="Blender pixel-centres; native nearest-endpoint raster quantization <= 0.5 pixel")


def render(output,name,azimuth,size):
    declaration=camera(azimuth,size)
    path=output/(name+"-transparent.png")
    bpy.context.scene.render.filepath=str(path.resolve())
    bpy.ops.render.render(write_still=True)
    raster=RasterInput.from_png_bytes(path.read_bytes())
    assert not raster.error,raster.error
    raw=bytes(round(c*255) for c in raster.rgba)
    beauty=bytearray(len(raw));mask=bytearray(len(raw))
    for i in range(0,len(raw),4):
        a=raw[i+3]/255
        beauty[i:i+4]=bytes((*(round(a*c+(1-a)*255) for c in raw[i:i+3]),255))
        value=255 if raw[i+3]>=128 else 0
        mask[i:i+4]=bytes((value,value,value,255))
    png(output/(name+".png"),size,size,beauty)
    png(output/(name+"-subject-mask.png"),size,size,mask)
    return declaration


def badge_masks(output):
    size=1024
    scene=bpy.context.scene
    camera(0,size)
    badge=bpy.data.objects[BADGE]
    corners=[badge.matrix_world@Vector(p) for p in badge.bound_box]
    xs=[int((p.x+1)*size/2) for p in corners];ys=[int((p.z+1)*size/2) for p in corners]
    exact=bytearray(size*size)
    depsgraph=bpy.context.evaluated_depsgraph_get()
    for y in range(max(0,min(ys)-2),min(size,max(ys)+3)):
        for x in range(max(0,min(xs)-2),min(size,max(xs)+3)):
            origin=Vector((2*(x+.5)/size-1,-6.,2*(y+.5)/size-1))
            hit,_,_,_,obj,_=scene.ray_cast(depsgraph,origin,Vector((0,1,0)),distance=12.)
            exact[y*size+x]=int(hit and obj.name==BADGE)
    expanded=bytearray(exact)
    for i,value in enumerate(exact):
        if value:
            x,y=i%size,i//size
            for dy in range(-2,3):
                for dx in range(-2,3):
                    if 0<=x+dx<size and 0<=y+dy<size:expanded[(y+dy)*size+x+dx]=1
    for name,values in (("badge-visible-mask",exact),("badge-edit-mask",expanded)):
        rgba=bytes(c for value in values for c in (255*value,255*value,255*value,255))
        png(output/(name+".png"),size,size,rgba)
    expected=RasterInput.from_png_bytes((output/"reference-front-transparent.png").read_bytes())
    actual=RasterInput.from_png_bytes((output/"target-wrong-badge-transparent.png").read_bytes())
    changed=[i for i in range(size*size) if expected.rgba[4*i:4*i+4]!=actual.rgba[4*i:4*i+4]]
    outside=sum(not expanded[i] for i in changed)
    assert changed and outside==0,(len(changed),outside)
    indices=[i for i,v in enumerate(exact) if v]
    bounds=[min(i%size for i in indices)/size,min(i//size for i in indices)/size,
            (max(i%size for i in indices)+1)/size,(max(i//size for i in indices)+1)/size]
    return dict(original_uv_bounds=bounds,visible_pixel_centres=sum(exact),edit_support_pixels=sum(expanded),
        edit_support_dilation_pixels=2,changed_pixels=len(changed),changed_outside_edit_support=outside,
        visible_mask_authority="Nearest scene.ray_cast hit equals badge_color, at each original front pixel centre.",
        edit_mask_authority="Visible geometry footprint expanded by 2 pixels for finite antialiasing; not inferred segmentation.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"tests/fixtures/diagnostics/provider-v1")
    parser.add_argument("--verify-glb-only",action="store_true")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    recipe=build_robot()
    expected=geometry()
    glb=output/"original-reference.glb"
    if args.verify_glb_only:
        reload_glb(glb,expected)
        print("GLB_RELOAD_VERIFIED",sha(glb.read_bytes()))
        return
    source=dict(schema_version=SCHEMA,asset_id="meshvenn-original-rounded-robot-v1",license="GPL-3.0-or-later",
        origin="Repository-owned mathematical Blender primitive authoring; no external or production assets.",
        human_validated=False,provider_calls=0,coordinate_space="Blender Z-up/native normalized cube [-1,1]",
        primitives=recipe,healthy_badge_linear_rgba=BADGE_HEALTHY,one_sided_feature="right_flag_only",
        expected_parts=sorted(expected),mesh_objects=len(expected),triangles=sum(v["triangles"] for v in expected.values()))
    write_json(output/"original-source.json",source)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj.type=="MESH":obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(glb),export_format="GLB",use_selection=True,export_animations=False,
                              export_cameras=False,export_lights=False,export_extras=True)
    assert glb.stat().st_size<2*1024*1024
    proof=reload_glb(glb,expected)
    write_json(output/"glb-reload-proof.json",proof)
    stage()
    cameras={name:render(output,"reference-"+name,angle,1024 if name=="front" else 512)
             for name,angle in (("front",0),("right",90),("back",180),("left",270))}
    before_geometry=geometry()
    badge=bpy.data.objects[BADGE]
    shader=badge.data.materials[0].node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value=BADGE_DEFECT
    render(output,"target-wrong-badge",0,1024)
    assert geometry()==before_geometry,"The injected defect changed geometry."
    mask=badge_masks(output)
    assets=[dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(output.iterdir())
            if p.is_file() and p.name!="manifestfixture.json"]
    manifest=dict(schema_version=SCHEMA,fixture_id="provider-rounded-robot-v1",frozen_before_provider=True,provider_calls=0,
        human_reviewed=False,provider_fidelity_qualified=False,corrected_3d_claim=False,license="GPL-3.0-or-later",
        authoring_script=dict(path="scripts/build_diagnostic_reference.py",sha256=sha(Path(__file__).read_bytes())),
        renderer=dict(blender=bpy.app.version_string,engine="CYCLES",device="CPU",samples=32,seed=17,max_bounces=1,exposure=-.65,
            diffuse_bounces=0,glossy_bounces=0,color_space="sRGB",view_transform="Standard",look="None",
            background="Transparent studio render composited onto opaque white; paired alpha-derived subject mask."),
        truth=dict(source="original-source.json",glb="original-reference.glb",reload="glb-reload-proof.json",
            all_reference_views_rendered_after_fresh_glb_import=True,geometry_identical_between_healthy_and_defect=True),
        provider_inputs=dict(healthy="reference-front-transparent.png",target="target-wrong-badge-transparent.png",
            edit_mask="badge-edit-mask.png",visible_mask="badge-visible-mask.png",width=1024,height=1024,
            transparent_background=True,selection_frozen_before_provider=True),
        cameras=cameras,defect=dict(target="target-wrong-badge-transparent.png",healthy="reference-front-transparent.png",object=BADGE,
            property="Principled BSDF Base Color only",healthy_linear_rgba=BADGE_HEALTHY,wrong_linear_rgba=BADGE_DEFECT,**mask),
        expected_observations_before_provider=["Only the visible chest badge has the wrong authored color.",
            "The body, face, limbs, silhouette, camera, background and one-sided right flag must remain unchanged.",
            "Front visible color can be compared. Hidden/back-facing badge evidence remains unknown.",
            "A 2D provider edit does not establish a corrected mesh or a correct final GLB.",
            "No human-reviewed or generative-provider identity qualification is claimed."],assets=assets)
    write_json(output/"manifestfixture.json",manifest)
    print("REFERENCE_FIXTURE_READY",output,"manifest_sha256",sha((output/"manifestfixture.json").read_bytes()))


if __name__=="__main__":main()
