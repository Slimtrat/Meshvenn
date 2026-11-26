"""Bounded Blender renders of reloaded GLBs in one source-defined frame."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys


def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
    return digest.hexdigest()


def _write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def _record(path,root):
    return {"path":Path(path).relative_to(root).as_posix(),"sha256":_sha(path),"bytes":Path(path).stat().st_size}


def render_comparison(assets:list[dict],output:Path,*,blender_executable:Path,
                      angles=(0,45,90,135,180,225,270,315),size=640,
                      timeout_seconds=900,modes=("flat","material"))->dict:
    """Copy exact inputs, reload in Blender, render and extract exported geometry.

    Assets: asset_id, label, role (source/candidate/reference), glb_path,
    glb_sha256. There is exactly one source. No asset is fitted independently.
    References are never silently promoted to candidates.
    """
    if type(size) is not int or not 128<=size<=2048:raise ValueError("size must be 128..2048")
    if not 1<=timeout_seconds<=3600:raise ValueError("timeout must be 1..3600 seconds")
    if not assets or len(assets)>32 or sum(a.get("role")=="source" for a in assets)!=1:
        raise ValueError("Exactly one source and at most 32 assets are required")
    if not angles or len(angles)>24 or any(not math.isfinite(a) for a in angles):raise ValueError("Invalid angles")
    if not modes or set(modes)-{"flat","material"}:raise ValueError("Unknown render mode")
    ids=[a.get("asset_id") for a in assets]
    if any(type(i) is not str or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",i) for i in ids) or len(set(ids))!=len(ids):
        raise ValueError("Asset IDs must be unique safe identifiers")
    checked=[]
    for asset in assets:
        path=Path(asset["glb_path"]).resolve(strict=True)
        if asset.get("role") not in ("source","candidate","reference"):raise ValueError("Invalid role")
        if not re.fullmatch("[a-f0-9]{64}",asset.get("glb_sha256","")) or _sha(path)!=asset["glb_sha256"]:
            raise ValueError("GLB SHA256 does not match: "+asset["asset_id"])
        checked.append(dict(asset,glb_path=str(path)))
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    (output/"assets").mkdir()
    for asset in checked:
        path=output/"assets"/(asset["asset_id"]+".glb")
        shutil.copyfile(asset["glb_path"],path)
        if _sha(path)!=asset["glb_sha256"]:raise ValueError("Copied GLB changed")
        asset["original_glb_path"]=asset["glb_path"]
        asset["glb_path"]=str(path)
    request={"schema_version":1,"assets":checked,"angles":list(angles),"size":size,"modes":list(modes),
             "output":str(output),"render_script_sha256":_sha(__file__)}
    request_path=output/"render-request.json";_write(request_path,request)
    command=[str(Path(blender_executable).resolve(strict=True)),"--background","--factory-startup",
             "--python",str(Path(__file__).resolve()),"--","--request",str(request_path)]
    with (output/"blender.stdout.log").open("wb") as out,(output/"blender.stderr.log").open("wb") as err:
        process=subprocess.Popen(command,stdout=out,stderr=err)
        try:code=process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=15)
            _write(output/"render-failure.json",{"status":"timed_out","timeout_seconds":timeout_seconds})
            raise TimeoutError("Blender render deadline exceeded; partial outputs retained")
    if code!=0:raise RuntimeError("Blender render failed; inspect retained blender.stderr.log")
    result=json.loads((output/"render-manifest.json").read_text(encoding="utf-8"))
    if result.get("request_sha256")!=_sha(request_path):raise ValueError("Render receipt does not match request")
    if result.get("status")!="completed" or [a["asset_id"] for a in result["assets"]]!=ids:
        raise ValueError("Incomplete render asset set")
    for asset in result["assets"]:
        original=next(a for a in checked if a["asset_id"]==asset["asset_id"])
        if asset["role"]!=original["role"] or asset["glb"]["sha256"]!=original["glb_sha256"]:
            raise ValueError("Render asset role or original GLB changed")
        if _sha(output/asset["glb"]["path"])!=asset["glb"]["sha256"]:raise ValueError("Rendered GLB changed")
        for record in [asset["mesh"],*asset["frames"]]:
            if _sha(output/record["path"])!=record["sha256"]:raise ValueError("Render evidence changed")
    return result


def _worker(request_path):
    import bpy
    from mathutils import Vector

    request=json.loads(Path(request_path).read_text(encoding="utf-8"));output=Path(request["output"])
    imported={}
    bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
    for asset in request["assets"]:
        if _sha(asset["glb_path"])!=asset["glb_sha256"]:raise ValueError("GLB changed before import")
        before=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=asset["glb_path"])
        objects=[o for o in bpy.data.objects if o not in before and o.type=="MESH"]
        if not objects:raise ValueError("Reloaded GLB has no mesh")
        imported[asset["asset_id"]]=objects
    source=next(a for a in request["assets"] if a["role"]=="source")
    source_objects=imported[source["asset_id"]]

    def geometry(objects):
        vertices=[];triangles=[];groups=[]
        depsgraph=bpy.context.evaluated_depsgraph_get()
        for obj in objects:
            evaluated=obj.evaluated_get(depsgraph);mesh=evaluated.to_mesh()
            try:
                offset=len(vertices);start=len(triangles)
                vertices.extend([list(evaluated.matrix_world@v.co) for v in mesh.vertices])
                mesh.calc_loop_triangles()
                triangles.extend([[offset+i for i in t.vertices] for t in mesh.loop_triangles])
                groups.append({"object_name":obj.name,"first_triangle":start,"triangle_count":len(triangles)-start,
                               "material_names":[m.name if m else None for m in mesh.materials]})
            finally:evaluated.to_mesh_clear()
        if not vertices or not triangles:raise ValueError("Reloaded GLB has no triangles")
        if any(not math.isfinite(v) for point in vertices for v in point):raise ValueError("Nonfinite GLB geometry")
        bounds={"minimum":[min(v[i] for v in vertices) for i in range(3)],
                "maximum":[max(v[i] for v in vertices) for i in range(3)]}
        return vertices,triangles,groups,bounds

    _,_,_,bounds=geometry(source_objects)
    minimum=Vector(bounds["minimum"]);maximum=Vector(bounds["maximum"])
    center=(minimum+maximum)/2;extent=maximum-minimum
    height=max(extent.z,0.01);width=math.hypot(extent.x,extent.y)
    scale=max(height,width)*1.16
    crops={"full":(center,scale),"head":(Vector((center.x,center.y,minimum.z+height*.86)),height*.42),
           "bust":(Vector((center.x,center.y,minimum.z+height*.68)),height*.76)}
    scene=bpy.context.scene
    scene.render.resolution_x=scene.render.resolution_y=request["size"]
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG";scene.render.image_settings.color_mode="RGB"
    scene.render.film_transparent=False
    scene.view_settings.view_transform="Standard"
    scene.view_settings.look="None"
    scene.world.color=(.16,.16,.16)
    camera_data=bpy.data.cameras.new("ReviewCamera");camera=bpy.data.objects.new("ReviewCamera",camera_data)
    scene.collection.objects.link(camera);scene.camera=camera;camera_data.type="ORTHO"
    camera_data.clip_start=.001;camera_data.clip_end=max(scale*100,100)
    for name,position,energy in (("key",(3,-4,5),500),("fill",(-4,-2,2),250),("rim",(1,4,4),350)):
        light_data=bpy.data.lights.new(name,"AREA");light_data.energy=energy*scale*scale/4;light_data.shape="DISK";light_data.size=scale*2
        light=bpy.data.objects.new(name,light_data);scene.collection.objects.link(light)
        light.location=center+Vector(position)*scale
        light.rotation_euler=(center-light.location).to_track_quat("-Z","Y").to_euler()
    # Use the same CPU backend for both modes, including on Linux without EGL.
    # A plain material plus flat polygon normals reveals geometry without an
    # OpenGL/Workbench dependency or changing the reloaded vertex positions.
    scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=8;scene.cycles.use_denoising=False
    clay=bpy.data.materials.new("ReviewGeometryClay");clay.use_nodes=True
    shader=clay.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value=(.56,.62,.7,1)
    shader.inputs["Roughness"].default_value=1
    result={"schema_version":1,"status":"partial","quality_status":"unknown","output_root":str(output),
            "request_sha256":_sha(request_path),"blender_version":bpy.app.version_string,
            "render_script_sha256":request["render_script_sha256"],
            "render_backend":{"engine":"CYCLES","device":"CPU","samples":8,"denoising":False,
                              "flat_mode":"plain material override and flat polygon normals"},
            "coordinate_frame":"Blender world coordinates after exact GLB reload; no per-asset fit or normalization",
            "source_bounds":bounds,"angles":request["angles"],"size":request["size"],"modes":request["modes"],
            "crop_policy":"Shared source-bounds full/head/bust crops; anatomical labels are visual prompts, not segmentation",
            "assets":[]}
    for asset in request["assets"]:
        objects=imported[asset["asset_id"]]
        vertices,triangles,groups,asset_bounds=geometry(objects)
        directory=output/asset["asset_id"];directory.mkdir()
        mesh_path=directory/"reloaded-mesh.json"
        _write(mesh_path,{"schema_version":1,"source_glb_sha256":asset["glb_sha256"],"coordinate_frame":result["coordinate_frame"],
                          "vertices":vertices,"triangles":triangles,"objects":groups,"bounds":asset_bounds})
        item={"asset_id":asset["asset_id"],"label":asset["label"],"role":asset["role"],
              "request_sha256":result["request_sha256"],
              "glb":_record(Path(asset["glb_path"]),output),"mesh":_record(mesh_path,output),
              "reload":{"verified":True,"source_glb_sha256":asset["glb_sha256"],"mesh_objects":len(objects),
                        "vertices":len(vertices),"triangles":len(triangles),"bounds":asset_bounds},"frames":[]}
        for group in imported.values():
            for obj in group:obj.hide_render=obj not in objects
        original_smooth={obj.name:[p.use_smooth for p in obj.data.polygons] for obj in objects}
        for mode in request["modes"]:
            if mode=="flat":
                scene.view_layers[0].material_override=clay
                scene.world.color=(.055,.065,.085)
                for obj in objects:
                    for poly in obj.data.polygons:poly.use_smooth=False
            else:
                scene.view_layers[0].material_override=None
                scene.world.color=(.16,.16,.16)
                for obj in objects:
                    for poly,smooth in zip(obj.data.polygons,original_smooth[obj.name]):poly.use_smooth=smooth
            views=[("full",a) for a in request["angles"]]+[("head",45),("bust",45)]
            for crop,angle in views:
                target,ortho=crops[crop];camera_data.ortho_scale=ortho
                radians=math.radians(angle);distance=scale*4
                camera.location=target+Vector((math.sin(radians)*distance,-math.cos(radians)*distance,0))
                camera.rotation_euler=(target-camera.location).to_track_quat("-Z","Y").to_euler()
                path=directory/f"{mode}-{crop}-{angle:g}.png"
                scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
                item["frames"].append(dict(_record(path,output),mode=mode,crop=crop,angle=angle,
                                           camera={"location":list(camera.location),"target":list(target),"ortho_scale":ortho}))
        if _sha(asset["glb_path"])!=asset["glb_sha256"]:raise ValueError("GLB changed during render")
        _write(directory/"reload-receipt.json",item)
        result["assets"].append(item)
        if len(result["assets"])==len(request["assets"]):result["status"]="completed"
        _write(output/"render-manifest.json",result)


if __name__=="__main__":
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    if len(args)!=2 or args[0]!="--request":raise SystemExit("Blender worker expects --request JSON")
    _worker(args[1])
