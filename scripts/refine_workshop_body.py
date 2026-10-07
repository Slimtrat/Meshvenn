"""Distinct authored-skin candidate and nineteen-pose proof; baseline stays immutable."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core.modular_character.json_io import strict_json_loads
from core.native_pose_capture import validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from scripts.author_stytch_doll import digest, module, remove_saved_previews, source_snapshot, write_json
from scripts.extract_stytch_pose_series import ASSET_SHA, INDEX_SHA256
from scripts.head_isolation_metrics import masked_edge_summary
from scripts.native_pose_replay import apply_probe
from scripts.replay_stytch_doll_pose import decoded_lbs, hausdorff
from scripts.render_v2_pipeline_preview import _camera, _import, _positions, _render
from scripts.workshop_doll_evidence import compare_owned_variant

RENDER_CASES = {"factory-hall", "factory-held", "Walk-meshvenn-walk-02", "Hop-meshvenn-hop-11"}


def poses():
    dataset = ROOT / "example/v2/poses/StytchDoll/complete"
    if digest(dataset / "index.json") != INDEX_SHA256:
        raise ValueError("The exact synchronized pose index changed.")
    index = strict_json_loads((dataset / "index.json").read_text("utf-8"))
    result = []
    for case in index["cases"]:
        paths = [(dataset / case[k]).resolve(strict=True) for k in ("probe", "matrix_proof")]
        for path, key in zip(paths, ("probe", "matrix_proof")):
            if path.parent != dataset.resolve() or digest(path) != case[key+"_sha256"]:
                raise ValueError("Unsafe or altered synchronized matrix input.")
        probe = NativePoseProbe.from_dict(strict_json_loads(paths[0].read_text("utf-8")))
        if probe.asset_sha256 != ASSET_SHA:
            raise ValueError("Unexpected captured baseline asset.")
        validate_matrix_proof(probe, strict_json_loads(paths[1].read_text("utf-8")))
        result.append((case, probe))
    if len(result) != 19 or len({c[0]["id"] for c in result}) != 19:
        raise ValueError("Require all nineteen exact poses.")
    return index, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-attempt", default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    fixture = ROOT / "example/v2/modular/StytchDoll"
    output = args.output.resolve()
    if output == fixture or fixture in output.parents or (output.exists() and any(output.iterdir())):
        raise ValueError("Choose a distinct empty candidate directory; the baseline is immutable.")
    baseline = strict_json_loads((fixture / "manifest.json").read_text("utf-8"))
    original = {name: digest(fixture / name) for name in ("source.blend", "authoring.json", "character.glb")}
    if original["character.glb"] != ASSET_SHA or original["source.blend"] != baseline["editable_source_sha256"]:
        raise ValueError("Baseline source/artifact fingerprint mismatch.")
    index, captures = poses()
    output.mkdir(parents=True, exist_ok=True)
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(fixture / "source.blend"), use_scripts=False)
        mesh, rig = bpy.data.objects["MeshvennScan"], bpy.data.objects["MeshvennCanonicalRig"]
        authority = source_snapshot(mesh, rig)
        spec = module("implementations.glb_export.face_authoring")._read(fixture / "authoring.json")
        remove_saved_previews(mesh, spec)
        mesh.hide_set(False)
        mesh.hide_render = False
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        rig.data.pose_position = "POSE"
        bpy.context.view_layer.update()
        rest = list(_positions((mesh,))[mesh.name])
        low, high = min(p[2] for p in rest), max(p[2] for p in rest)
        height = high-low
        center = (max(p[0] for p in rest)+min(p[0] for p in rest))/2
        torso = [.45 <= (p[2]-low)/height <= .67 and abs(p[0]-center)/height <= .14 for p in rest]
        mesh.data.calc_loop_triangles()
        triangles = [tuple(t.vertices) for t in mesh.data.loop_triangles]
        before = {}
        evidence = output / "poses"
        evidence.mkdir()
        if not args.no_render:
            _camera((mesh,), 768, 32)
            _render(evidence / "rest.png")
        for case, probe in captures:
            apply_probe(rig, probe)
            points = list(_positions((mesh,))[mesh.name])
            before[case["id"]] = masked_edge_summary(rest, points, triangles, torso, height)
            if not args.no_render and case["id"] in RENDER_CASES:
                _render(evidence / (case["id"]+"-baseline.png"))
        assert source_snapshot(mesh, rig) == authority
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        bpy.context.view_layer.update()
        assert bpy.ops.bpt.refine_owned_skin() == {"FINISHED"}
        edit = strict_json_loads(mesh["meshvenn_owned_skin_refinement"])
        refined = source_snapshot(mesh, rig)
        assert authority["weights"] != refined["weights"]
        assert {k: v for k, v in authority.items() if k != "weights"} == {k: v for k, v in refined.items() if k != "weights"}
        for name in ("authoring.json", "partition-authoring.json", "reference.glb"):
            shutil.copy2(fixture / name, output / name)
        settings = bpy.context.scene.bpt_settings
        settings.export_modular_character = True
        settings.export_modular_manifest_path = str(output / "authoring.json")
        settings.export_output_path = str(output / "character.glb")
        settings.export_overwrite_existing = False
        forbidden = (("implementations.projection_images", "ProjectionImagesImplementation"),
                     ("implementations.native_visual_hull", "NativeVisualHullImplementation"),
                     ("implementations.uv_bake", "UVBakeImplementation"),
                     ("implementations.canonical_rig_v2", "CanonicalRigV2Implementation"),
                     ("implementations.canonical_motion", "CanonicalMotionRetargetImplementation"))
        with ExitStack() as guards:
            for name, cls in forbidden:
                guards.enter_context(patch.object(getattr(module(name), cls), "execute", side_effect=AssertionError("No Rebuild required")))
            assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
        assert source_snapshot(mesh, rig) == refined
        context = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
        exported = context.require_output(module("core.pipeline_contracts").PipelineStage.EXPORT)
        reader = module("implementations.glb_export.modular_gltf")
        old, old_binary = reader.read_glb(fixture / "character.glb")
        new, new_binary = reader.read_glb(exported.path)
        proof = compare_owned_variant(old, old_binary, new, new_binary, reader.read_accessor)
        assert old["asset"]["extras"]["meshvenn_modular_character"]["spec"] == new["asset"]["extras"]["meshvenn_modular_character"]["spec"]
        assert not new.get("animations")
        # Save an editable rest-state source before importing temporary evidence.
        settings.export_modular_manifest_path = "//authoring.json"
        settings.export_output_path = "//character.glb"
        preview_context = module("implementations.glb_export.modular_source").context_from_authored_scene(
            bpy.context.scene, output_path=str(output / "preview-only.glb"))
        plan = module("implementations.glb_export.planning").build_export_plan(preview_context)
        with module("implementations.glb_export.modular_partition").prepare_modular_meshes(plan, spec):
            mesh.hide_set(True)
            mesh.hide_render = True
            bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"), compress=True, relative_remap=False)
        mesh.hide_set(False)
        mesh.hide_render = False
        after, decoded = [], {}
        for case, probe in captures:
            apply_probe(rig, probe)
            points = list(_positions((mesh,))[mesh.name])
            current = masked_edge_summary(rest, points, triangles, torso, height)
            raw, rest_error = decoded_lbs(new, new_binary, probe, reader)
            decoded[case["id"]] = raw
            error = hausdorff(points, raw)
            assert error < 2e-5*height
            after.append({"id": case["id"], "probe_sha256": case["probe_sha256"],
                "matrix_proof_sha256": case["matrix_proof_sha256"], "hidden_regions": case["hidden_regions"],
                "baseline_torso_edges": before[case["id"]], "candidate_torso_edges": current,
                "source_vs_decoded_max_error_m": error, "rest_world_matrix_max_error": rest_error})
            if not args.no_render and case["id"] in RENDER_CASES:
                _render(evidence / (case["id"]+"-source-candidate.png"))
        assert source_snapshot(mesh, rig) == refined
        meshes, rigs = _import(exported.path)
        if not args.no_render:
            _camera(meshes, 768, 32)
        for result, (case, probe) in zip(after, captures):
            apply_probe(rigs[0], probe)
            positions = _positions(meshes)
            points = [p for part in meshes for p in positions[part.name]]
            result["decoded_vs_reimport_max_error_m"] = hausdorff(decoded[case["id"]], points)
            assert result["decoded_vs_reimport_max_error_m"] < 2e-5*height
            for part in meshes:
                part.hide_render = False
            if not args.no_render and case["id"] in RENDER_CASES:
                _render(evidence / (case["id"]+"-glb-candidate.png"))
                for region in case["hidden_regions"]:
                    next(part for part in meshes if part.name == "Doll_"+region.replace("-", "_")).hide_render = True
                if case["hidden_regions"]:
                    _render(evidence / (case["id"]+"-glb-absent-limbs.png"))
        improvements = all(r["candidate_torso_edges"]["outside_20_percent_count"] <= .5*r["baseline_torso_edges"]["outside_20_percent_count"]
                           and r["candidate_torso_edges"]["p95_abs_log_length_ratio"] <= .7*r["baseline_torso_edges"]["p95_abs_log_length_ratio"] for r in after)
        report = {"passed": improvements, "source_sha": args.source_sha, "run_id": args.run_id, "run_attempt": args.run_attempt,
            "baseline": original, "candidate": {"source.blend": digest(output / "source.blend"),
                "authoring.json": digest(output / "authoring.json"), "character.glb": exported.sha256},
            "pose_set_sha256": INDEX_SHA256, "consumer_pose_revision": index["source_revision"],
            "captured_asset_sha256": ASSET_SHA, "candidate_uses_identical_native_rest_frames": True,
            "intentional_source_weight_edit": edit, "surface_and_material_proof": proof,
            "case_count": len(after), "cases": after, "torso_metric_improves_in_every_pose": improvements,
            "torso_regression_gate": "Frozen cohort: at least 50% fewer edges outside [0.8,1.2] length ratio and 30% lower p95 absolute log strain in every pose. Not anatomical or visual acceptance.",
            "visual_qualification": False, "consumer_acceptance": False,
            "images": {p.name: digest(p) for p in evidence.glob("*.png")},
            "scope": "Intentional source-only skin edit. Exact old pose matrices reused only after identical native rests/binds are proved. No consumer geometry/weight repair, contact certification or appearance rebake."}
        write_json(output / "pose-quality.json", report)
        assert improvements, "Authored skin did not improve both frozen torso metrics in every captured pose."
        manifest = {**baseline, "source_asset": "stytch_workshop_doll_authored_skin_v1",
            "sha256": exported.sha256, "editable_source_sha256": digest(output / "source.blend"),
            "contract": new["asset"]["extras"]["meshvenn_modular_character"],
            "pipeline": "pinned native source -> explicit authored axial/collar weight edit -> prepared No Rebuild modular export",
            "source_authority_unchanged": False, "selected_refined_source_unchanged_during_export": True,
            "source_authority_sha256": hashlib.sha256(json.dumps(refined, sort_keys=True, allow_nan=False).encode()).hexdigest(),
            "baseline_artifact_sha256": ASSET_SHA, "body_refinement": edit,
            "reference_role": "OLD accepted baseline with old weights; not the selected-source weight oracle",
            "reference_fidelity": proof, "roundtrip": exported.metadata["roundtrip"]["modular_character"],
            "pose_quality_report_sha256": digest(output / "pose-quality.json"),
            "consumer_acceptance": "Distinct candidate, NOT replayed or accepted by Stytch.",
            "remaining_limits": ["Native rest pivots unchanged; neck and attachment quality not fully qualified.",
                                 "Original two-view atlas coverage and UV overlap unchanged; appearance unqualified."]}
        write_json(output / "manifest.json", manifest)
        assert all(digest(fixture / name) == value for name, value in original.items())
        print(f"Authored skin candidate: {edit['changed_vertex_count']} source vertices edited; 19 fidelity poses pass; all-pose torso metric improvement={improvements}; visual/consumer acceptance pending.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
