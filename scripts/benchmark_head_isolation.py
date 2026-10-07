"""Measure and render actual GLB head isolation; neck limits remain explicit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.render_v2_pipeline_preview import _camera, _import, _positions, _render
from scripts.v2_preview_evidence import digest
from scripts.head_isolation_metrics import masked_edge_summary, rigid_residual

POSES = {
    "left_arm": {"upper_arm.L": ((0, 0, 1), -.75), "forearm.L": ((0, 0, 1), -.8)},
    "right_arm": {"upper_arm.R": ((0, 0, 1), .75), "forearm.R": ((0, 0, 1), .8)},
    "chest_twist": {"chest": ((0, 1, 0), .3)},
    "head_yaw": {"head": ((0, 1, 0), .6)},
    "head_pitch": {"head": ((0, 0, 1), .4)},
    "neck_pitch": {"neck": ((0, 0, 1), .3)},
    "compound": {"chest": ((0, 1, 0), .15), "upper_arm.L": ((0, 0, 1), -.25),
                 "forearm.L": ((0, 0, 1), -.55), "upper_arm.R": ((0, 0, 1), .18),
                 "thigh.L": ((1, 0, 0), .22), "shin.L": ((1, 0, 0), -.35)},
}


def probe(fixture, output, label):
    manifest = json.loads((fixture / "manifest.json").read_text("utf-8"))
    assert digest(fixture / "character.glb") == manifest["sha256"]
    meshes, rigs = _import(fixture / "character.glb")
    assert len(meshes) == 5 and len(rigs) == 1 and len(rigs[0].data.bones) == 18
    rig = rigs[0]
    rig.data.pose_position = "POSE"
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()
    rest_by_mesh = _positions(meshes)
    rest, triangles = [], []
    for mesh in meshes:
        start = len(rest)
        rest.extend(rest_by_mesh[mesh.name])
        mesh.data.calc_loop_triangles()
        triangles.extend(tuple(start+i for i in t.vertices) for t in mesh.data.loop_triangles)
    assert len(triangles) == 14252
    floor = min(p[2] for p in rest)
    height = max(p[2] for p in rest)-floor
    # Source-specific frozen test cohorts, NOT inferred anatomy or ownership.
    head = [(p[2]-floor)/height >= .73 for p in rest]
    neck = [.65 <= (p[2]-floor)/height <= .75 for p in rest]
    head_rest = (rig.matrix_world @ rig.data.bones["head"].matrix_local).inverted()
    _camera(meshes, 768, 32)
    _render(output / f"{label}_rest.png")
    result = []
    for name, rotations in POSES.items():
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        for bone_name, (axis, angle) in rotations.items():
            bone = rig.pose.bones[bone_name]
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = Quaternion(Vector(axis), angle)
        bpy.context.view_layer.update()
        posed_by_mesh = _positions(meshes)
        posed = [p for mesh in meshes for p in posed_by_mesh[mesh.name]]
        delta = rig.matrix_world @ rig.pose.bones["head"].matrix @ head_rest
        expected = [tuple(delta @ Vector(p)) for p in rest]
        result.append({"id": name, "head_rigid": rigid_residual(rest, posed, expected, head, height),
                       "head_edges": masked_edge_summary(rest, posed, triangles, head, height),
                       "neck_edges": masked_edge_summary(rest, posed, triangles, neck, height)})
        if name in ("compound", "head_pitch"):
            _render(output / f"{label}_{name}.png")
    return {"artifact_sha256": manifest["sha256"], "poses": result, "height_m": height,
            "head_cohort": "frozen rest normalized Z >= 0.73",
            "neck_cohort": "frozen rest normalized Z in [0.65, 0.75]"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "example/v2/modular/StytchDoll")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", default="local-uncommitted")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-attempt", default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty evidence directory.")
    output.mkdir(parents=True, exist_ok=True)
    baseline = probe(args.baseline.resolve(), output, "baseline")
    candidate = probe(args.candidate.resolve(), output, "candidate")
    old_worst = max(p["head_rigid"]["max_residual_in_heights"] for p in baseline["poses"])
    new_worst = max(p["head_rigid"]["max_residual_in_heights"] for p in candidate["poses"])
    passed = (old_worst > .01 and new_worst < 2e-5
              and all(p["head_edges"]["edge_count"] > 1000
                      and p["head_edges"]["max_abs_log_length_ratio"] < .001 for p in candidate["poses"]))
    images = {p.name: digest(p) for p in sorted(output.glob("*.png"))}
    report = {"passed": passed, "source_sha": args.source_sha, "run_id": args.run_id,
              "run_attempt": args.run_attempt, "rendered_from_final_glb": True,
              "pose_kind": "seven explicit native-joint probes, NOT imported animation clips",
              "rotations": POSES, "baseline": baseline, "candidate": candidate,
              "max_head_rigid_residual_reduction": 1-new_worst/old_worst,
              "images": images, "neck_quality_qualified": False, "full_appearance_qualified": False,
              "limits": "Original rest head/neck pivots, two-view atlas coverage and UV overlap retained. Neck strain is reported, NOT hidden or qualified."}
    (output / "quality.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", "utf-8")
    assert passed, "Actual GLB head isolation quality gate failed."
    print(f"Head isolation PASS: {len(POSES)} probes; worst head rigid error {old_worst:.6g} -> {new_worst:.6g} heights; neck/artistic limits explicit.")


if __name__ == "__main__":
    main()
