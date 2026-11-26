"""Real production Native/Surface Nets comparisons, run inside Blender.

Only source masks are derived from the original GLB. Candidate vertices come
from the native DLL and the existing bounded contour-taubin-v2 implementation.
No source-surface fit, anatomy inference, rig or export-quality certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.character_quality.camera_profiles import LEGACY_CAMERAS, DENSE_CAMERAS, DENSE_PROFILE

# Native positive elevation views from -Z; names describe physical camera sides.
ANGLES=LEGACY_CAMERAS


def _write(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    temporary=path.with_suffix(path.suffix+".pending")
    temporary.write_bytes(raw);temporary.replace(path)


def _selected(count,views):
    if count==2:return tuple(v for v in views if v["id"] in ("az000","az090"))
    return tuple(views[:count])


def reconstruct_cases(output,native_library,*,source_glb=None,resolution=64,mask_size=256,view_counts=(2,8,10),hero_size=768):
    """Create a NEW output directory; publish an incremental manifest and assets.

    Returns manifest metadata with relative {path,sha256,bytes} artifact records.
    Native local vertices retain production units until a fixed envelope-to-cube
    presentation transform. No candidate-specific resize or alignment is fitted.
    """
    if type(resolution) is not int or not 16<=resolution<=128:raise ValueError("Resolution must be 16..128.")
    if type(mask_size) is not int or not 32<=mask_size<=512:raise ValueError("Mask raster must be 32..512.")
    if type(hero_size) is not int or not 64<=hero_size<=1024:raise ValueError("Hero raster must be 64..1024.")
    counts=tuple(view_counts)
    if not counts or len(set(counts))!=len(counts) or any(type(n) is not int or n not in (2,8,10,18) for n in counts):
        raise ValueError("View counts must be unique members of 2,8,10,18.")
    library=Path(native_library).resolve()
    source=Path(source_glb or ROOT/"tests/fixtures/diagnostics/provider-v1/original-reference.glb").resolve()
    if not library.is_file() or not source.is_file():raise ValueError("Existing native library and source GLB are required.")
    provenance=dict(kind="caller-supplied GLB",license="unspecified")
    if source_glb is None:
        from scripts.diagnostic_qualification.reference import verify_fixture
        archived=verify_fixture(source.parent)
        provenance=dict(kind="repository-owned mathematical Blender source",license="GPL-3.0-or-later",
            repository_path=source.relative_to(ROOT).as_posix(),fixture_manifest_sha256=archived["manifest_sha256"])
    import bpy
    from core.native_bridge import NativeCore,NativeProjection
    from core.native_scan_trace import scan_named_projections
    from core.contour_surface import ContourSurface
    from core.geometry_contracts import GeometryProjectionSpace
    from core.native_mesh_builder import create_blender_mesh_from_native,shade_smooth_native_object
    from core.surface_refinement import refine_native_surface
    from scripts.character_quality.blender_scene import record,load,inventory,ray_masks,neutral,hero,export_and_reload
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    original=source.read_bytes();(out/"source.glb").write_bytes(original)
    meshes=load(out/"source.glb");source_info=inventory(meshes)[0]
    if any(a < -1.000002 or b > 1.000002 for a,b in zip(*source_info["bounds"])):
        raise ValueError("Source world surface must already be in the declared normalized cube; no hidden source fit is performed.")
    mask_dir=out/"masks";mask_dir.mkdir()
    views,_=ray_masks(meshes,mask_dir,mask_size,DENSE_CAMERAS if 18 in counts else ANGLES)
    public_views=[{k:v for k,v in view.items() if k!="mask"} for view in views]
    source_hero=out/"source.hero.png";hero(out/"source.glb",source_hero,hero_size)
    source_sha=hashlib.sha256(original).hexdigest()
    manifest=dict(schema_version=1,complete=False,source=dict(id="owned_robot" if source_glb is None else source.stem,role="source",
        original_sha256=source_sha,provenance=provenance,glb=record(out/"source.glb",out),hero=record(source_hero,out),
        reload=dict(source_glb_sha256=source_sha,verified=True,reloaded_in_empty_scene=True,**source_info)),
        native_library=dict(filename=library.name,sha256=hashlib.sha256(library.read_bytes()).hexdigest(),expected_abi=1),
        cameras=public_views,cases=[],requested=dict(resolution=resolution,mask_size=mask_size,view_counts=counts,hero_size=hero_size),
        comparison_frame=dict(coordinates="native normalized cube [-1,+1], Z-up",source_fit=False,
            hero_camera=dict(azimuth_degrees=45.,elevation_degrees=-15.,ortho_scale=2.5,width=hero_size,height=hero_size),
            material="Common neutral gray; source colors deliberately separated from geometry review.",normals="Smooth presentation for source and all candidates."),
        scope=dict(actual_reconstruction=True,plain_static_glb=True,rig_certified=False,source_mesh_used_for_candidate_fit=False),
        generator=dict(blender=bpy.app.version_string,source_files=[dict(path=name,
            sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()) for name in (
                "scripts/character_quality/reconstruct.py","scripts/character_quality/blender_scene.py",
                "scripts/character_quality/camera_profiles.py")]),
        implementation_sources=[dict(path=name,sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()) for name in (
            "core/native_bridge/runtime.py","core/native_scan_trace.py","core/surface_refinement.py","core/contour_surface.py",
            "core/native_mesh_builder.py","core/projection_frame.py")])
    _write(out/"manifest.json",manifest)
    core=NativeCore(library);cache={}
    for count in counts:
        selected=_selected(count,views)
        started=time.monotonic()
        trace=scan_named_projections(core,((v["id"],NativeProjection(v["mask"],v["azimuth_degrees"],v["elevation_degrees"])) for v in selected),
            resolution=resolution,symmetry_x=False,thread_count=0)
        if not trace.volume.occupied_count:raise ValueError("Source silhouettes produced an empty native hull.")
        raw=core.build_surface_mesh(trace.volume,voxel_size=1.,center_xy=True,mesh_mode="surface_nets")
        space=GeometryProjectionSpace(resolution,resolution,resolution,voxel_size=1.,center_xy=True)
        for finish in ("none","organic"):
            begin=time.monotonic()
            active=tuple(SimpleNamespace(name=v["id"],mask=v["mask"],azimuth_degrees=v["azimuth_degrees"],
                elevation_degrees=v["elevation_degrees"],flip_x=False) for v in selected)
            contour=ContourSurface.from_views(active,space,cache=cache) if finish=="organic" else None
            mesh,refinement=refine_native_surface(raw,voxel_size=1.,mode=finish,mesh_mode="surface_nets",contour_surface=contour)
            bpy.ops.wm.read_factory_settings(use_empty=True)
            identifier=f"views{count:02d}_{finish}"
            obj=create_blender_mesh_from_native(mesh,mesh_name=identifier,object_name=identifier)
            shade_smooth_native_object(obj);neutral((obj,))
            obj.scale=(2/resolution,)*3;obj.location.z=-1.
            obj["character_quality_source"]="Native Surface Nets silhouette reconstruction; no source-surface substitution."
            path=out/(identifier+".glb")
            reload=export_and_reload(obj,path)
            hero_path=out/(identifier+".hero.png");hero(path,hero_path,hero_size)
            case=dict(id=identifier,role="candidate",glb=record(path,out),hero=record(hero_path,out),reload=reload,
                resolution=resolution,view_ids=[v["id"] for v in selected],surface_refinement=finish,refinement=refinement,
                input_camera_profile=DENSE_PROFILE if count==18 else "native-cube-legacy-input-v1",
                native_mesh=dict(vertices=mesh.vertex_count,polygons=mesh.polygon_count,
                    vertices_sha256=hashlib.sha256(mesh.vertices.tobytes()).hexdigest(),
                    indices_sha256=hashlib.sha256(mesh.indices.tobytes()).hexdigest()),
                native_volume=dict(dimensions=[resolution]*3,occupied_voxels=trace.volume.occupied_count,
                    sha256=hashlib.sha256(trace.volume.values).hexdigest(),bounds=trace.volume.bounds),
                view_trace=[v.as_dict() for v in trace.views],elapsed_seconds=time.monotonic()-begin,
                canonical_transform=dict(scale=2/resolution,translation=[0.,0.,-1.],authority="GeometryProjectionSpace.surface-envelope-v1",per_case_fit=False))
            _write(out/(identifier+".json"),case);manifest["cases"].append(case);_write(out/"manifest.json",manifest)
            print("CHARACTER_QUALITY_CASE_READY",identifier,str(path),flush=True)
        print("CHARACTER_QUALITY_VIEWSET_SECONDS",count,time.monotonic()-started,flush=True)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=source_sha:raise ValueError("Original GLB evidence changed.")
    manifest["complete"]=True;_write(out/"manifest.json",manifest)
    print("CHARACTER_QUALITY_COMPLETE",str(out/"manifest.json"),flush=True)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--native-library",type=Path,required=True)
    parser.add_argument("--source-glb",type=Path);parser.add_argument("--resolution",type=int,default=64)
    parser.add_argument("--mask-size",type=int,default=256);parser.add_argument("--hero-size",type=int,default=768)
    parser.add_argument("--view-counts",type=int,nargs="+",default=[2,8,10])
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:])
    reconstruct_cases(args.output,args.native_library,source_glb=args.source_glb,resolution=args.resolution,
        mask_size=args.mask_size,view_counts=args.view_counts,hero_size=args.hero_size)


if __name__=="__main__":main()
