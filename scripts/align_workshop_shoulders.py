"""Distinct two-pivot delivery with transparently rest-relative derived pose evidence."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parent))
from scripts.author_stytch_doll import digest, module, remove_saved_previews, source_snapshot
from scripts.refine_workshop_body import poses, RENDER_CASES
from scripts.shoulder_pose_derivation import derive_pose, document
from scripts.native_pose_replay import AXES, apply_probe
from scripts.replay_stytch_doll_pose import decoded_lbs, hausdorff
from scripts.render_v2_pipeline_preview import _camera, _import, _positions, _render
from scripts.head_isolation_metrics import masked_edge_summary
from scripts.workshop_doll_evidence import compare_shoulder_variant
from core.rig_owned_skin import _surface_distances
from core.native_pose_probe import NativePoseProbe

BASE_SHA = "dc0ba1f2129d09754f0ff53cf609a709338a6946acf1f8f341c8ae4624e4e9bc"
SOURCE_SHA = "69bb7e8af073c53703dd3e76cc6a1bce72fe7aea5b1628f8ea2d5e661243c724"


def write_json(path,value):
    # Fingerprinted evidence is reproducible across Git checkouts and OSes.
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")


def native_local_rests(rig):
    return {b.name:tuple(tuple(row) for row in (b.parent.matrix_local.inverted() @ b.matrix_local
             if b.parent else AXES @ b.matrix_local)) for b in rig.data.bones}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--no-render",action="store_true")
    parser.add_argument("--run-id",default=None)
    parser.add_argument("--run-attempt",default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    fixture,output = ROOT / "example/v2/modular/StytchDollAuthoredSkin",args.output.resolve()
    if fixture == output or fixture in output.parents or output.exists() and any(output.iterdir()):
        raise ValueError("Choose a distinct empty candidate directory; keep the baseline immutable.")
    if digest(fixture / "character.glb") != BASE_SHA or digest(fixture / "source.blend") != SOURCE_SHA:
        raise ValueError("Authored-skin source/GLB fingerprint mismatch.")
    baseline = json.loads((fixture / "manifest.json").read_text("utf-8"))
    index,captures = poses()
    output.mkdir(parents=True,exist_ok=True)
    images,derived_dir = output / "poses",output / "derived-poses"
    images.mkdir()
    derived_dir.mkdir()
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(fixture / "source.blend"),use_scripts=False)
        mesh,rig = bpy.data.objects["MeshvennScan"],bpy.data.objects["MeshvennCanonicalRig"]
        before = source_snapshot(mesh,rig)
        spec = module("implementations.glb_export.face_authoring")._read(fixture / "authoring.json")
        remove_saved_previews(mesh,spec)
        mesh.hide_set(False)
        mesh.hide_render = False
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        rig.data.pose_position = "POSE"
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        bpy.context.view_layer.update()
        rest = list(_positions((mesh,))[mesh.name])
        height = max(p[2] for p in rest)-min(p[2] for p in rest)
        vertices = [tuple(v.co) for v in mesh.data.vertices]
        low,high = min(p[2] for p in vertices),max(p[2] for p in vertices)
        native_height = high-low
        role_map = {r.id:r.role for r in spec.regions}
        keys,_,distances,_ = _surface_distances(vertices,[tuple(p.vertices) for p in mesh.data.polygons],
            [role_map[r] for r in spec.ownership[mesh.name]],native_height)
        masks = {role:[distances[role].get(k,math.inf) <= .10 for k in keys] for role in ("left-arm","right-arm")}
        masks["neck"] = [.65 <= (p[2]-low)/native_height <= .80 and abs(p[0])/native_height <= .12 for p in vertices]
        mesh.data.calc_loop_triangles()
        triangles = [tuple(t.vertices) for t in mesh.data.loop_triangles]
        unchanged_skin = [not any(g.weight > 0 and mesh.vertex_groups[g.group].name.startswith("upper_arm.") for g in v.groups) for v in mesh.data.vertices]
        before_points,before_quality = {},{}
        if not args.no_render:
            _camera((mesh,),768,32)
        for case,probe in captures:
            apply_probe(rig,probe)
            points = list(_positions((mesh,))[mesh.name])
            before_points[case["id"]] = points
            before_quality[case["id"]] = {name:masked_edge_summary(rest,points,triangles,mask,height) for name,mask in masks.items()}
            if not args.no_render and case["id"] in RENDER_CASES:
                _render(images / (case["id"]+"-baseline.png"))
        assert source_snapshot(mesh,rig) == before
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        bpy.context.view_layer.update()
        assert bpy.ops.bpt.align_authored_shoulders() == {"FINISHED"}
        edit = json.loads(mesh["meshvenn_shoulder_alignment"])
        selected = source_snapshot(mesh,rig)
        assert {k:v for k,v in before.items() if k != "bones"} == {k:v for k,v in selected.items() if k != "bones"}
        new_rests = native_local_rests(rig)
        # JSON values/ownership stay exact, but successor bytes are canonical LF.
        # Historical Windows CRLF fingerprints are not portable Git fingerprints.
        for name in ("authoring.json","partition-authoring.json"):
            (output / name).write_text((fixture / name).read_text("utf-8"),encoding="utf-8",newline="\n")
        shutil.copy2(fixture / "reference.glb",output / "reference.glb")
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
        assert source_snapshot(mesh,rig) == selected
        pipeline = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
        exported = pipeline.require_output(module("core.pipeline_contracts").PipelineStage.EXPORT)
        reader = module("implementations.glb_export.modular_gltf")
        old,old_binary = reader.read_glb(fixture / "character.glb")
        new,binary = reader.read_glb(exported.path)
        proof = compare_shoulder_variant(old,old_binary,new,binary,reader.read_accessor)
        assert old["asset"]["extras"]["meshvenn_modular_character"]["spec"] == new["asset"]["extras"]["meshvenn_modular_character"]["spec"]
        settings.export_modular_manifest_path = "//authoring.json"
        settings.export_output_path = "//character.glb"
        preview = module("implementations.glb_export.modular_source").context_from_authored_scene(bpy.context.scene,output_path=str(output / "preview-only.glb"))
        plan = module("implementations.glb_export.planning").build_export_plan(preview)
        with module("implementations.glb_export.modular_partition").prepare_modular_meshes(plan,spec):
            mesh.hide_set(True)
            mesh.hide_render = True
            bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"),compress=True,relative_remap=False)
        mesh.hide_set(False)
        mesh.hide_render = False
        if not args.no_render:
            _render(images / "rest.png")
        results,decoded,derived = [],{},{}
        for case,probe in captures:
            candidate = derive_pose(probe,new_rests,exported.sha256)
            derived[case["id"]] = candidate
            path = derived_dir / (case["id"]+".json")
            write_json(path,document(candidate))
            apply_probe(rig,candidate)
            points = list(_positions((mesh,))[mesh.name])
            raw,rest_error = decoded_lbs(new,binary,candidate,reader)
            decoded[case["id"]] = raw
            source_error = hausdorff(points,raw)
            unchanged_error = max(math.dist(a,b) for a,b,keep in zip(before_points[case["id"]],points,unchanged_skin) if keep)
            assert source_error < 2e-5*height and unchanged_error < 2e-5*height
            quality = {name:masked_edge_summary(rest,points,triangles,mask,height) for name,mask in masks.items()}
            results.append({"id":case["id"],"probe_sha256":case["probe_sha256"],"matrix_proof_sha256":case["matrix_proof_sha256"],
                "hidden_regions":case["hidden_regions"],"derived_pose_sha256":digest(path),"baseline_cohorts":before_quality[case["id"]],
                "candidate_cohorts":quality,"source_vs_decoded_max_error_m":source_error,"rest_world_matrix_max_error":rest_error,
                "vertices_without_shoulder_influence_max_error_m":unchanged_error})
            if not args.no_render and case["id"] in RENDER_CASES:
                _render(images / (case["id"]+"-source-candidate.png"))
        assert source_snapshot(mesh,rig) == selected
        meshes,rigs = _import(exported.path)
        if not args.no_render:
            _camera(meshes,768,32)
        for result,(case,_) in zip(results,captures):
            apply_probe(rigs[0],derived[case["id"]])
            positions = _positions(meshes)
            points = [p for part in meshes for p in positions[part.name]]
            result["decoded_vs_reimport_max_error_m"] = hausdorff(decoded[case["id"]],points)
            assert result["decoded_vs_reimport_max_error_m"] < 2e-5*height
            for part in meshes:
                part.hide_render = False
            if not args.no_render and case["id"] in RENDER_CASES:
                _render(images / (case["id"]+"-glb-candidate.png"))
                for region in case["hidden_regions"]:
                    next(part for part in meshes if part.name == "Doll_"+region.replace("-","_")).hide_render = True
                if case["hidden_regions"]:
                    _render(images / (case["id"]+"-glb-absent-limbs.png"))
        improved = all(r["candidate_cohorts"][name]["p95_abs_log_length_ratio"] <= .8*r["baseline_cohorts"][name]["p95_abs_log_length_ratio"]
                       for r in results for name in ("left-arm","right-arm"))
        readable = all(r["candidate_cohorts"][name]["collapsed_fraction"] == 0 for r in results if r["id"] in {"factory-hall","factory-held"} for name in masks)
        assert improved and readable, "The observed shoulder correction did not improve every pose or eliminate Hall/held collapsed cohorts."
        report = {"passed":True,"source_sha":args.source_sha,"run_id":args.run_id,"run_attempt":args.run_attempt,
            "baseline_sha256":BASE_SHA,"baseline_source_sha256":SOURCE_SHA,"pose_set_sha256":digest(ROOT / "example/v2/poses/StytchDoll/complete/index.json"),
            "consumer_pose_revision":index["source_revision"],"candidate_sha256":exported.sha256,
            "editable_source_sha256":digest(output / "source.blend"),"authoring_sha256":digest(output / "authoring.json"),
            "case_count":len(results),"cases":results,"shoulder_metric_improves_every_pose":improved,
            "hall_held_collapsed_cohorts_eliminated":readable,"visual_qualification":False,"consumer_acceptance":False,
            "derivation":"Evidence-only: new parent-local Pose = new Rest * inverse(old captured Rest) * old captured Pose. Original capture/proof unchanged; not a new Stytch capture or pixel-equality claim.",
            "shoulder_refinement":edit,"surface_skin_material_proof":proof,"images":{p.name:digest(p) for p in images.glob("*.png")}}
        write_json(output / "pose-quality.json",report)
        manifest = {**baseline,"source_asset":"stytch_workshop_doll_shoulder_aligned_v1","sha256":exported.sha256,
            "editable_source_sha256":digest(output / "source.blend"),"source_authority_sha256":hashlib.sha256(json.dumps(selected,sort_keys=True,allow_nan=False).encode()).hexdigest(),
            "authoring_sha256":digest(output / "authoring.json"),"partition_authoring_sha256":digest(output / "partition-authoring.json"),
            "authoring_byte_policy":"Successor JSON uses UTF-8 LF on every OS; parsed authoring/partition values equal the baseline. Historical generated-input CRLF fingerprints are not claimed as current delivered-file fingerprints.",
            "body_refinement_scope":"Historical preceding weight edit only; its unchanged-rest statement does not describe this later shoulder-rest correction.",
            "baseline_artifact_sha256":BASE_SHA,"contract":new["asset"]["extras"]["meshvenn_modular_character"],
            "pipeline":"pinned authored-skin source -> explicit observed shoulder rest origins -> prepared No Rebuild export",
            "reference_fidelity":proof,"shoulder_refinement":edit,"native_rest_revision":edit["algorithm"],
            "roundtrip":exported.metadata["roundtrip"]["modular_character"],"pose_quality_report_sha256":digest(output / "pose-quality.json"),
            "consumer_acceptance":"Distinct candidate, NOT replayed or accepted by Stytch.",
            "remaining_limits":["Derived poses are NOT consumer captures of this new rest rig; Stytch acceptance remains required.",
                                "Legacy elbow/hip/head joint placement and general pose quality are not certified.",
                                "Original atlas fallback/UV overlap and intentionally open absent-limb seams remain unchanged."]}
        write_json(output / "manifest.json",manifest)
        assert digest(fixture / "character.glb") == BASE_SHA and digest(fixture / "source.blend") == SOURCE_SHA
        print("Shoulder-aligned candidate PASS: 19 derived pose transports, all-pose shoulder improvement, Hall/held collapsed cohorts removed; consumer acceptance pending.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
