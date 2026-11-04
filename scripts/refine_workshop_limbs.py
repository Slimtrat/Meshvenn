"""Pinned distal native-chain correction with isolated and actual-pose evidence."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT.parent))
from core.native_pose_capture import validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from core.rig_owned_skin import _surface_distances
from core.rig_limb_chain import CHAINS
from scripts.author_stytch_doll import digest, module, remove_saved_previews, source_snapshot
from scripts.extract_stytch_pose_series import capture_profile
from scripts.glb_v2_pose_metrics import joint_edge_summary
from scripts.glb_v2_pose_support import rotated_bone
from scripts.head_isolation_metrics import masked_edge_summary
from scripts.native_pose_replay import AXES, apply_probe
from scripts.render_v2_pipeline_preview import _import, _positions, _render
from scripts.render_turntable import create_camera, look_at, setup_lighting, setup_render
from scripts.replay_stytch_doll_pose import decoded_lbs, hausdorff
from scripts.workshop_doll_evidence import compare_limb_variant

BASE_SHA = "6654f85acb539e471ccc525f4ffc029409e96e98aeb524df1be95211e860d3f8"
SOURCE_SHA = "7d424323bfb70d7cd5abdd36af034ea30f30c210989f35677ef7b4049c71adbd"
RENDER_CASES = {"factory-hall", "factory-held", "Walk-meshvenn-walk-02", "Hop-meshvenn-hop-11"}


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")


def captures():
    profile = capture_profile("shoulder-aligned")
    dataset = profile["dataset"].resolve(strict=True)
    if digest(dataset / "index.json") != profile["index_sha256"]:
        raise ValueError("Fresh captured pose index changed.")
    index = json.loads((dataset / "index.json").read_text("utf-8"))
    if index["source_revision"] != profile["revision"] or index["asset_sha256"] != BASE_SHA:
        raise ValueError("Wrong selected-asset capture lineage.")
    result = []
    for case in index["cases"]:
        paths = [(dataset / case[key]).resolve(strict=True) for key in ("probe", "matrix_proof")]
        for path, key in zip(paths,("probe", "matrix_proof")):
            if path.parent != dataset or digest(path) != case[key+"_sha256"]:
                raise ValueError("Unsafe or changed captured matrices.")
        probe = NativePoseProbe.from_dict(json.loads(paths[0].read_text("utf-8")))
        if probe.asset_sha256 != BASE_SHA:
            raise ValueError("Capture targets a different original asset.")
        validate_matrix_proof(probe,json.loads(paths[1].read_text("utf-8")))
        result.append((case,probe))
    if len(result) != 19 or len({c[0]["id"] for c in result}) != 19:
        raise ValueError("Require nineteen exact fresh captures.")
    return index,result


def reset(rig):
    for bone in rig.pose.bones: bone.matrix_basis.identity()
    rig.data.pose_position = "POSE"
    bpy.context.view_layer.update()


def isolated(mesh,rig,rest,triangles,height,centers):
    reset(rig)
    results = []
    for family,axes in (("thigh",(("X",(1,0,0)),)), ("shin",(("X",(1,0,0)),)),
                        ("forearm",(("Y",(0,1,0)),("Z",(0,0,1))))):
        for side in ("L","R"):
            name = family+"."+side
            for label,axis in axes:
                for angle in (-90,-45,45,90):
                    with rotated_bone(rig,name,angle,axis,world_space=True):
                        points = list(_positions((mesh,))[mesh.name])
                    results.append({"id":f"{name}/{label}/{angle:+d}","bone":name,
                        "axis":label,"angle_degrees":angle,
                        "edges":joint_edge_summary(rest,points,triangles,centers[name],height,touching=True)})
    return results



def root_rigidity(mesh,rig,rest,height,masks):
    reset(rig)
    results = []
    for role,chain in CHAINS.items():
        selected = masks[role]
        axis = (0,1,0) if "arm" in role else (1,0,0)
        for angle in (-90,90):
            with rotated_bone(rig,chain[0],angle,axis,world_space=True):
                points = list(_positions((mesh,))[mesh.name])
                bone = rig.pose.bones[chain[0]]
                delta = rig.matrix_world @ bone.matrix @ bone.bone.matrix_local.inverted() @ rig.matrix_world.inverted()
                residual = max(math.dist(points[i],tuple(delta @ Vector(rest[i]))) for i in selected)/height
            results.append({"role":role,"root":chain[0],"angle_degrees":angle,
                            "vertex_count":len(selected),"max_rigid_residual_in_heights":residual})
    return results


def loaded(path, probe, hidden):
    meshes,rigs = _import(path)
    apply_probe(rigs[0],probe)
    for mesh in meshes:
        mesh.hide_render = mesh.name in {"Doll_"+r.replace("-","_") for r in hidden}
    points = [p for mesh in meshes if not mesh.hide_render for p in _positions((mesh,))[mesh.name]]
    return meshes,points


def render_pairs(before_path,after_path,selected,output):
    """Use one union frame and identical lights for both sides of each comparison."""
    images = output / "poses"
    images.mkdir()
    for case,probe in selected:
        if case["id"] not in RENDER_CASES: continue
        _,a = loaded(before_path,probe,case["hidden_regions"])
        _,b = loaded(after_path,probe,case["hidden_regions"])
        points = a+b
        lower = Vector(tuple(min(p[i] for p in points) for i in range(3)))
        upper = Vector(tuple(max(p[i] for p in points) for i in range(3)))
        target,dimensions = (lower+upper)*.5,upper-lower
        radius = dimensions.length
        for variant,path in (("baseline",before_path),("candidate",after_path)):
            loaded(path,probe,case["hidden_regions"])
            setup_lighting(dimensions)
            lights = [o for o in bpy.context.scene.objects if o.type == "LIGHT"]
            for light in lights:
                light.location += target
                light.data.energy *= max(max(dimensions),1)**2
            offsets = [(light,light.location.copy()-target) for light in lights]
            setup_render(size=768,samples=32)
            camera = create_camera(target=target,model_size=dimensions)
            camera.data.ortho_scale = radius*1.15
            for view,direction in (("front",Vector((1.5,-2.6,.35))), ("back",Vector((-1.5,2.6,.35)))):
                camera.location = target+direction*radius
                look_at(camera,target)
                sign = 1 if view == "front" else -1
                for light,offset in offsets:
                    light.location = target+Vector((sign*offset.x,sign*offset.y,offset.z))
                    look_at(light,target)
                _render(images / f"{case['id']}-{variant}-{view}.png")
    return {p.name:digest(p) for p in images.glob("*.png")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--no-render",action="store_true")
    parser.add_argument("--run-id",default=None)
    parser.add_argument("--run-attempt",default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    fixture,output = ROOT / "example/v2/modular/StytchDollShoulderAligned",args.output.resolve()
    if fixture == output or fixture in output.parents or output.exists() and any(output.iterdir()):
        raise ValueError("Choose a distinct fresh output directory; all preceding bundles stay immutable.")
    if digest(fixture / "character.glb") != BASE_SHA or digest(fixture / "source.blend") != SOURCE_SHA:
        raise ValueError("Pinned shoulder-aligned source/GLB changed.")
    baseline = json.loads((fixture / "manifest.json").read_text("utf-8"))
    index,selected = captures()
    output.mkdir(parents=True,exist_ok=True)
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(fixture / "source.blend"),use_scripts=False)
        mesh,rig = bpy.data.objects["MeshvennScan"],bpy.data.objects["MeshvennCanonicalRig"]
        spec = module("implementations.glb_export.face_authoring")._read(fixture / "authoring.json")
        remove_saved_previews(mesh,spec)
        reset(rig)
        before = source_snapshot(mesh,rig)
        rest = list(_positions((mesh,))[mesh.name])
        floor,height = min(p[2] for p in rest),max(p[2] for p in rest)-min(p[2] for p in rest)
        mesh.data.calc_loop_triangles()
        triangles = [tuple(t.vertices) for t in mesh.data.loop_triangles]
        centers = {b.name:tuple(rig.matrix_world @ b.head) for b in rig.pose.bones}
        torso = [.45 <= (p[2]-floor)/height <= .67 and abs(p[0])/height <= .14 for p in rest]

        native_points = [tuple(v.co) for v in mesh.data.vertices]
        native_height = max(p[2] for p in native_points)-min(p[2] for p in native_points)
        role_by_id = {r.id:r.role for r in spec.regions}
        native_roles = [role_by_id[r] for r in spec.ownership[mesh.name]]
        keys,members,distances,_ = _surface_distances(native_points,[tuple(f.vertices) for f in mesh.data.polygons],native_roles,native_height)
        collar = json.loads(mesh["meshvenn_owned_skin_refinement"])["collar_in_heights"]
        masks = {role:[i for i,key in enumerate(keys) if members[key] == {role} and distances[role][key] >= 2*collar] for role in CHAINS}
        tri_roles = [native_roles[t.polygon_index] for t in mesh.data.loop_triangles]
        before_rigid = root_rigidity(mesh,rig,rest,height,masks)
        before_iso = isolated(mesh,rig,rest,triangles,height,centers)
        original_points,original_torso,original_hips,original_visible_hips,original_visible_joints,original_owned_joints = {},{},{},{},{},{}
        review_joints = [family+"."+side for family in ("thigh","shin","forearm") for side in ("L","R")]
        joint_roles = {name:("left-" if name.endswith(".L") else "right-")+("arm" if name.startswith("forearm") else "leg") for name in review_joints}
        for case,probe in selected:
            apply_probe(rig,probe)
            points = list(_positions((mesh,))[mesh.name])
            original_points[case["id"]] = points
            original_torso[case["id"]] = masked_edge_summary(rest,points,triangles,torso,height)
            original_hips[case["id"]] = {s:joint_edge_summary(rest,points,triangles,centers["thigh."+s],height,touching=True) for s in ("L","R")}
            visible = [t for t,role in zip(triangles,tri_roles) if role not in case["hidden_regions"]]
            original_visible_hips[case["id"]] = {s:joint_edge_summary(rest,points,visible,centers["thigh."+s],height,touching=True) for s in ("L","R")}
            original_visible_joints[case["id"]] = {name:joint_edge_summary(rest,points,visible,centers[name],height,touching=True) for name in review_joints}
            original_owned_joints[case["id"]] = {name:joint_edge_summary(rest,points,
                [t for t,role in zip(triangles,tri_roles) if role in {"body-core",joint_roles[name]}],centers[name],height,touching=True)
                for name in review_joints if joint_roles[name] not in case["hidden_regions"]}
        assert source_snapshot(mesh,rig) == before
        reset(rig)
        mesh.hide_set(False); mesh.hide_render = False
        bpy.ops.object.select_all(action="DESELECT"); mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        assert bpy.ops.bpt.refine_distal_limb_skin() == {"FINISHED"}
        edit = json.loads(mesh["meshvenn_distal_limb_refinement"])
        refined = source_snapshot(mesh,rig)
        assert {k:v for k,v in before.items() if k != "weights"} == {k:v for k,v in refined.items() if k != "weights"}
        protected = [a == b for a,b in zip(before["weights"],refined["weights"])]
        allowed_positions = [tuple(AXES @ mesh.matrix_world @ v.co) for v,keep in zip(mesh.data.vertices,protected) if not keep]
        write_json(output / "edited-source-positions.json",allowed_positions)
        after_rigid = root_rigidity(mesh,rig,rest,height,masks)
        for a,b in zip(before_rigid,after_rigid):
            assert a["role"] == b["role"] and a["vertex_count"] == b["vertex_count"]
            assert b["max_rigid_residual_in_heights"] < 2e-6
            if a["max_rigid_residual_in_heights"] > 1e-4:
                assert b["max_rigid_residual_in_heights"] <= .01*a["max_rigid_residual_in_heights"]
        after_iso = isolated(mesh,rig,rest,triangles,height,centers)
        for a,b in zip(before_iso,after_iso):
            assert a["edges"]["edge_count"] == b["edges"]["edge_count"]
            assert b["edges"]["max_abs_log_length_ratio"] <= 1.01*a["edges"]["max_abs_log_length_ratio"]+1e-4, (a["id"],a["edges"],b["edges"])
            assert b["edges"]["p95_abs_log_length_ratio"] <= 1.01*a["edges"]["p95_abs_log_length_ratio"]+1e-4
            assert b["edges"]["collapsed_fraction"] <= a["edges"]["collapsed_fraction"]+1e-10
        for name in ("authoring.json","partition-authoring.json","reference.glb"):
            shutil.copy2(fixture / name,output / name)
        settings = bpy.context.scene.bpt_settings
        settings.export_modular_manifest_path = str(output / "authoring.json")
        settings.export_output_path = str(output / "character.glb")
        settings.export_overwrite_existing = False
        forbidden = (("implementations.projection_images","ProjectionImagesImplementation"),
                     ("implementations.native_visual_hull","NativeVisualHullImplementation"),
                     ("implementations.uv_bake","UVBakeImplementation"),
                     ("implementations.canonical_rig_v2","CanonicalRigV2Implementation"),
                     ("implementations.canonical_motion","CanonicalMotionRetargetImplementation"))
        with ExitStack() as guards:
            for name,cls in forbidden:
                guards.enter_context(patch.object(getattr(module(name),cls),"execute",side_effect=AssertionError("No Rebuild required")))
            assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
        assert source_snapshot(mesh,rig) == refined
        context = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
        exported = context.require_output(module("core.pipeline_contracts").PipelineStage.EXPORT)
        reader = module("implementations.glb_export.modular_gltf")
        old,old_binary = reader.read_glb(fixture / "character.glb")
        new,binary = reader.read_glb(exported.path)
        proof = compare_limb_variant(old,old_binary,new,binary,reader.read_accessor,allowed_positions)
        assert old["asset"]["extras"]["meshvenn_modular_character"]["spec"] == new["asset"]["extras"]["meshvenn_modular_character"]["spec"]
        assert not new.get("animations")
        settings.export_modular_manifest_path = "//authoring.json"
        settings.export_output_path = "//character.glb"
        preview = module("implementations.glb_export.modular_source").context_from_authored_scene(bpy.context.scene,output_path=str(output / "preview.glb"))
        plan = module("implementations.glb_export.planning").build_export_plan(preview)
        with module("implementations.glb_export.modular_partition").prepare_modular_meshes(plan,spec):
            mesh.hide_set(True); mesh.hide_render = True
            bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"),compress=True,relative_remap=False)
        mesh.hide_set(False); mesh.hide_render = False
        cases,decoded = [],{}
        for case,probe in selected:
            apply_probe(rig,probe)
            points = list(_positions((mesh,))[mesh.name])
            raw,rest_error = decoded_lbs(new,binary,probe,reader)
            error = hausdorff(points,raw)
            protected_error = max(math.dist(a,b) for a,b,keep in zip(original_points[case["id"]],points,protected) if keep)
            assert error < 2e-5*height and protected_error < 2e-5*height and rest_error < 2e-6
            hips = {s:joint_edge_summary(rest,points,triangles,centers["thigh."+s],height,touching=True) for s in ("L","R")}
            visible = [t for t,role in zip(triangles,tri_roles) if role not in case["hidden_regions"]]
            visible_hips = {s:joint_edge_summary(rest,points,visible,centers["thigh."+s],height,touching=True) for s in ("L","R")}
            visible_joints = {name:joint_edge_summary(rest,points,visible,centers[name],height,touching=True) for name in review_joints}
            owned_joints = {name:joint_edge_summary(rest,points,
                [t for t,role in zip(triangles,tri_roles) if role in {"body-core",joint_roles[name]}],centers[name],height,touching=True)
                for name in review_joints if joint_roles[name] not in case["hidden_regions"]}
            for name,measurement in owned_joints.items():
                previous = original_owned_joints[case["id"]][name]
                assert measurement["max_abs_log_length_ratio"] <= 1.01*previous["max_abs_log_length_ratio"]+1e-4, (case["id"],name,previous,measurement)
                assert measurement["collapsed_fraction"] <= previous["collapsed_fraction"]+1e-10
            for side in ("L","R"):
                previous = original_visible_hips[case["id"]][side]
                assert visible_hips[side]["max_abs_log_length_ratio"] <= previous["max_abs_log_length_ratio"]+1e-4
                assert visible_hips[side]["collapsed_fraction"] <= previous["collapsed_fraction"]+1e-10

            torso_edges = masked_edge_summary(rest,points,triangles,torso,height)
            assert abs(torso_edges["p95_abs_log_length_ratio"]-original_torso[case["id"]]["p95_abs_log_length_ratio"]) < 1e-4
            cases.append({"id":case["id"],"probe_sha256":case["probe_sha256"],"matrix_proof_sha256":case["matrix_proof_sha256"],
                "hidden_regions":case["hidden_regions"],"baseline_hip_edges":original_hips[case["id"]],"candidate_hip_edges":hips,
                "baseline_visible_hip_edges":original_visible_hips[case["id"]],"candidate_visible_hip_edges":visible_hips,
                "baseline_visible_joint_edges":original_visible_joints[case["id"]],"candidate_visible_joint_edges":visible_joints,
                "baseline_owned_joint_edges":original_owned_joints[case["id"]],"candidate_owned_joint_edges":owned_joints,
                "baseline_torso_edges":original_torso[case["id"]],"candidate_torso_edges":torso_edges,
                "source_vs_decoded_max_error_m":error,"rest_world_matrix_max_error":rest_error,
                "protected_vertices_pose_max_error_m":protected_error})
            decoded[case["id"]] = raw
        assert source_snapshot(mesh,rig) == refined
        meshes,rigs = _import(exported.path)
        for result,(case,probe) in zip(cases,selected):
            apply_probe(rigs[0],probe)
            points = [p for row in _positions(meshes).values() for p in row]
            result["decoded_vs_reimport_max_error_m"] = hausdorff(decoded[case["id"]],points)
            assert result["decoded_vs_reimport_max_error_m"] < 2e-5*height
        images = render_pairs(fixture / "character.glb",exported.path,selected,output) if not args.no_render else {}
        report = {"passed":True,"source_sha":args.source_sha,"run_id":args.run_id,"run_attempt":args.run_attempt,
            "baseline_sha256":BASE_SHA,"captured_asset_sha256":BASE_SHA,"candidate_sha256":exported.sha256,
            "editable_source_sha256":digest(output / "source.blend"),"pose_set_sha256":capture_profile("shoulder-aligned")["index_sha256"],
            "edited_source_positions_sha256":digest(output / "edited-source-positions.json"),
            "consumer_pose_revision":index["source_revision"],"case_count":len(cases),"cases":cases,
            "isolated_baseline":before_iso,"isolated_candidate":after_iso,
            "root_rigid_baseline":before_rigid,"root_rigid_candidate":after_rigid,"limb_chain_refinement":edit,
            "native_rests_and_captured_matrices_unchanged":True,"consumer_capture_targets_candidate":False,
            "visual_qualification":False,"consumer_acceptance":False,"images":images,
            "isolated_gate":"Eight distal root rotations: rigid residual <2e-6 heights and >=99% reduction where previously >1e-4. Thirty-two fixed joint cohorts: at most 1% relative p95/worst-strain increase (+1e-4 arithmetic allowance), no extra collapsed fraction. Actual present-owned joint cohorts: worst-strain bound +1%, no extra collapsed fraction; p95 remains diagnostic and may redistribute. Cross-limb visible-ball diagnostics, including absent joint locations, stay separately recorded. This is a real bounded tradeoff, not universal visual improvement.",
            "scope":"Source-only distal limb skin edit, same original captured matrices/rests. Candidate is not a newly captured or accepted Stytch asset. No material overlay, pose repair, world squash or contact claim."}
        write_json(output / "pose-quality.json",report)
        manifest = {**baseline,"source_asset":"stytch_workshop_doll_distal_chains_v1","sha256":exported.sha256,
            "editable_source_sha256":digest(output / "source.blend"),"source_authority_sha256":hashlib.sha256(json.dumps(refined,sort_keys=True,allow_nan=False).encode()).hexdigest(),
            "source_authority_unchanged":False,"selected_refined_source_unchanged_during_export":True,
            "pipeline":"pinned shoulder-aligned source -> explicit distal native-chain skin cleanup -> prepared No Rebuild export",
            "baseline_artifact_sha256":BASE_SHA,"limb_chain_refinement":edit,"reference_fidelity":proof,
            "edited_source_positions_sha256":digest(output / "edited-source-positions.json"),
            "body_refinement_scope":"Historical preceding body edit; this successor changes only declared limb rows beyond its attachment collars.",
            "roundtrip":exported.metadata["roundtrip"]["modular_character"],"pose_quality_report_sha256":digest(output / "pose-quality.json"),
            "consumer_acceptance":"Distinct distal-chain candidate, NOT replayed or accepted by Stytch.",
            "remaining_limits":["Distal rigid-chain fidelity is not full pose, articulation, anatomy or artistic acceptance.",
                "Captured matrices target the old skin; a newly selected consumer replay is still required.",
                "Existing elbow/knee/head fit, atlas fallback/UV overlap, open absent-limb seams and consumer squash remain unqualified."]}
        write_json(output / "manifest.json",manifest)
        assert digest(fixture / "character.glb") == BASE_SHA and digest(fixture / "source.blend") == SOURCE_SHA
        print("Distal limb candidate PASS: rigid native chains, isolated controls, nineteen actual-matrix transports; consumer acceptance pending.")
    finally:
        package.unregister()


if __name__ == "__main__": main()
