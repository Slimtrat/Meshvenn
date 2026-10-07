"""Actual reimported workshop doll; compound pose probe, not an animation claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.render_v2_pipeline_preview import (
    _camera, _import, _joint_world, _module, _positions, _render,
    _socket_positions, _socket_render,
)
from scripts.v2_preview_evidence import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", default="local-uncommitted")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-attempt", default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    fixture, output = args.fixture.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty preview directory; existing renders are not overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixture / "manifest.json").read_text("utf-8"))
    assert digest(fixture / "character.glb") == manifest["sha256"]
    meshes, rigs = _import(fixture / "reference.glb")
    assert len(meshes) == 1 and len(rigs) == 1 and len(rigs[0].data.bones) == 18
    rigs[0].data.pose_position = "REST"
    _camera(meshes, 768, 32)
    _render(output / "source.png")
    meshes, rigs = _import(fixture / "character.glb")
    assert len(meshes) == 5 and len(rigs) == 1 and len(rigs[0].data.bones) == 18
    rig = rigs[0]
    document, _ = _module("implementations.glb_export.modular_gltf").read_glb(fixture / "character.glb")
    assert not document.get("animations")
    envelope = document["asset"]["extras"]["meshvenn_modular_character"]
    assert envelope == manifest["contract"]
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    rest = _positions(meshes)
    _camera(meshes, 768, 32)
    _render(output / "rest.png")
    world = _joint_world(document)
    matrices = _socket_positions(rig, envelope, world)
    _socket_render(meshes, matrices, output / "sockets_rest.png")
    pose = {"chest": ((0, 1, 0), .15), "upper_arm.L": ((0, 0, 1), -.25),
            "forearm.L": ((0, 0, 1), -.55), "upper_arm.R": ((0, 0, 1), .18),
            "thigh.L": ((1, 0, 0), .22), "shin.L": ((1, 0, 0), -.35)}
    rig.data.pose_position = "POSE"
    for name, (axis, angle) in pose.items():
        bone = rig.pose.bones[name]
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = Quaternion(Vector(axis), angle)
    bpy.context.view_layer.update()
    posed = _positions(meshes)
    displacement = max((Vector(a) - Vector(b)).length for name in rest for a, b in zip(rest[name], posed[name]))
    assert displacement > .01
    _render(output / "compound.png")
    hidden = next(obj for obj in meshes if obj.name == "Doll_left_arm")
    hidden.hide_render = True
    _render(output / "hidden_left_arm.png")
    hidden.hide_render = False
    _socket_render(meshes, _socket_positions(rig, envelope, world), output / "sockets_compound.png")
    names = ("source.png", "rest.png", "compound.png", "hidden_left_arm.png", "sockets_rest.png", "sockets_compound.png")
    report = {"source_sha": args.source_sha, "run_id": args.run_id, "run_attempt": args.run_attempt,
              "artifact_sha256": manifest["sha256"],
              "reference_sha256": digest(fixture / "reference.glb"), "rendered_from_final_glb": True,
              "pose_kind": "explicit compound native-joint probe, NOT an imported animation",
              "pose": pose, "maximum_deformation_m": displacement, "images": {name: digest(output / name) for name in names},
              "scope": "Appearance remains the original two-view bake; X-ray socket materials are diagnostic-only."}
    (output / "preview.json").write_text(json.dumps(report, indent=2), "utf-8")
    print("Workshop doll actual GLB preview PASS; static compound probe explicitly labelled.")


if __name__ == "__main__":
    main()
