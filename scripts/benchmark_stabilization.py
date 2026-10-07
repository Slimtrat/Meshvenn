"""Behavior-preserving consolidation on the unchanged doll and exact pose set."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import shutil
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core.modular_character.json_io import strict_json_loads
from core.native_pose_capture import validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from scripts.author_stytch_doll import digest, module, source_snapshot, write_json
from scripts.extract_stytch_pose_series import ASSET_SHA, INDEX_SHA256
from scripts.head_isolation_metrics import masked_edge_summary
from scripts.native_pose_replay import apply_probe
from scripts.replay_stytch_doll_pose import decoded_lbs, hausdorff
from scripts.render_v2_pipeline_preview import _import, _positions
from scripts.workshop_doll_evidence import compare_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-attempt", default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    fixture = ROOT / "example/v2/modular/StytchDoll"
    dataset = ROOT / "example/v2/poses/StytchDoll/complete"
    output = args.output.resolve()
    if output == fixture or fixture in output.parents or (output.exists() and any(output.iterdir())):
        raise ValueError("Choose a separate empty evidence directory; the accepted source is immutable.")
    if digest(fixture / "character.glb") != ASSET_SHA or digest(dataset / "index.json") != INDEX_SHA256:
        raise ValueError("Baseline or synchronized pose set changed; explicitly select and qualify another pair.")
    index = strict_json_loads((dataset / "index.json").read_text("utf-8"))
    captures = []
    for case in index["cases"]:
        paths = [(dataset / case[k]).resolve(strict=True) for k in ("probe", "matrix_proof")]
        for path, key in zip(paths, ("probe", "matrix_proof")):
            if path.parent != dataset.resolve() or digest(path) != case[key+"_sha256"]:
                raise ValueError("Captured matrix/provenance bytes changed.")
        probe = NativePoseProbe.from_dict(strict_json_loads(paths[0].read_text("utf-8")))
        if probe.asset_sha256 != ASSET_SHA:
            raise ValueError("Pose targets a different asset fingerprint.")
        validate_matrix_proof(probe, strict_json_loads(paths[1].read_text("utf-8")))
        captures.append((case, probe))
    assert len(captures) == 19 and len({c[0]["id"] for c in captures}) == 19
    original = {name: digest(fixture / name) for name in ("source.blend", "authoring.json", "character.glb")}
    manifest = strict_json_loads((fixture / "manifest.json").read_text("utf-8"))
    if original["source.blend"] != manifest["editable_source_sha256"]:
        raise ValueError("Editable baseline differs from its declared source fingerprint.")
    output.mkdir(parents=True, exist_ok=True)
    relocated = output / "relocated"
    relocated.mkdir()
    for name in ("source.blend", "authoring.json"):
        shutil.copy2(fixture / name, relocated / name)
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(relocated / "source.blend"), use_scripts=False)
        settings = bpy.context.scene.bpt_settings
        settings.export_output_path = "//candidate.glb"
        mesh, rig = bpy.data.objects["MeshvennScan"], bpy.data.objects["MeshvennCanonicalRig"]
        authority = source_snapshot(mesh, rig)
        import hashlib
        assert hashlib.sha256(json.dumps(authority, sort_keys=True, allow_nan=False).encode()).hexdigest() == manifest["source_authority_sha256"]
        assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
        assert source_snapshot(mesh, rig) == authority
        exported = module("operators.runtime").get_last_pipeline_context(bpy.context.scene).require_output(
            module("core.pipeline_contracts").PipelineStage.EXPORT)
        transport = exported.metadata["roundtrip"]["modular_character"]
        assert transport["passed"] and transport["raw_normal_tolerance"] == 2e-6
        reader = module("implementations.glb_export.modular_gltf")
        old, old_binary = reader.read_glb(fixture / "character.glb")
        new, new_binary = reader.read_glb(exported.path)
        proof = compare_reference(old, old_binary, new, new_binary, reader.read_accessor)
        assert proof["max_weight_error"] == proof["max_inverse_bind_error"] == 0
        assert old["asset"]["extras"]["meshvenn_modular_character"]["spec"] == new["asset"]["extras"]["meshvenn_modular_character"]["spec"]
        assert not old.get("animations") and not new.get("animations")
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        rig.data.pose_position = "POSE"
        bpy.context.view_layer.update()
        rest = list(_positions((mesh,))[mesh.name])
        floor = min(p[2] for p in rest)
        height = max(p[2] for p in rest)-floor
        center = (min(p[0] for p in rest)+max(p[0] for p in rest))/2
        torso = [.45 <= (p[2]-floor)/height <= .67 and abs(p[0]-center)/height <= .14 for p in rest]
        mesh.data.calc_loop_triangles()
        triangles = [tuple(t.vertices) for t in mesh.data.loop_triangles]
        native, raw_candidate, results = {}, {}, []
        for case, probe in captures:
            apply_probe(rig, probe)
            native[case["id"]] = list(_positions((mesh,))[mesh.name])
            before, _ = decoded_lbs(old, old_binary, probe, reader)
            after, _ = decoded_lbs(new, new_binary, probe, reader)
            difference = hausdorff(before, after)
            native_error = hausdorff(native[case["id"]], after)
            assert difference < 2e-5*height and native_error < 2e-5*height
            raw_candidate[case["id"]] = after
            results.append({"id": case["id"], "probe_sha256": case["probe_sha256"],
                "matrix_proof_sha256": case["matrix_proof_sha256"], "hidden_regions": case["hidden_regions"],
                "before_after_decoded_max_error_m": difference, "native_candidate_max_error_m": native_error,
                "torso_edges": masked_edge_summary(rest, native[case["id"]], triangles, torso, height)})
        assert source_snapshot(mesh, rig) == authority
        meshes, rigs = _import(exported.path)
        for result, (case, probe) in zip(results, captures):
            apply_probe(rigs[0], probe)
            positions = _positions(meshes)
            points = [p for part in meshes for p in positions[part.name]]
            result["candidate_reimport_max_error_m"] = hausdorff(raw_candidate[case["id"]], points)
            assert result["candidate_reimport_max_error_m"] < 2e-5*height
        assert all(digest(fixture / name) == value for name, value in original.items())
        assert all(digest(relocated / name) == original[name] for name in ("source.blend", "authoring.json"))
        report = {"passed": True, "source_sha": args.source_sha, "run_id": args.run_id,
            "run_attempt": args.run_attempt, "blender_version": bpy.app.version_string,
            "baseline": original, "candidate": {"source.blend": digest(relocated / "source.blend"),
                "authoring.json": digest(relocated / "authoring.json"), "character.glb": digest(exported.path)},
            "pose_set_sha256": INDEX_SHA256, "consumer_pose_revision": index["source_revision"],
            "surface_skin_and_bind_proof": proof, "transport_fidelity": transport,
            "cases": results, "case_count": len(results), "source_authority_unchanged": True,
            "posed_quality_qualified": False, "consumer_acceptance": False,
            "scope": "Behavior-preserving structural consolidation, not a source skin correction. Original upstream posed visual failure retained; #60 acceptance remains separate."}
        write_json(output / "stabilization.json", report)
        print("Stabilization PASS: exact surface/weights/binds/regions/sockets; nineteen poses preserve behavior; visual/consumer acceptance still pending.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
