"""Issue #60: native-source versus GLB replay of exact consumer pose matrices."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.modular_character.json_io import strict_json_loads
from core.native_pose_probe import NativePoseProbe
from scripts.author_stytch_doll import digest, module, source_snapshot
from scripts.head_isolation_metrics import masked_edge_summary
from scripts.native_pose_replay import AXES, accumulated, apply_probe, matrix_error
from scripts.render_v2_pipeline_preview import _camera, _import, _joint_world, _positions, _render


def hausdorff(a, b):
    def directed(left, right):
        tree = KDTree(len(right))
        for i,p in enumerate(right):
            tree.insert(p, i)
        tree.balance()
        return max(tree.find(p)[2] for p in left)
    return max(directed(a, b), directed(b, a))


def decoded_lbs(document, binary, probe, reader):
    """Independent CPU evaluation of stored glTF POSITION/WEIGHTS/binds."""
    world = _joint_world(document)
    skin = document["skins"][0]
    names = [document["nodes"][i]["name"] for i in skin["joints"]]
    captured_rest, captured_pose = accumulated(probe, rest=True), accumulated(probe)
    root_node = skin["joints"][names.index("root")]
    ancestor = world(root_node) @ captured_rest["root"].inverted()
    rest_error = max(matrix_error(world(i), ancestor @ captured_rest[name]) for name,i in zip(names, skin["joints"]))
    if rest_error > 2e-6:
        raise ValueError(f"Consumer rest differs from pinned GLB frame: {rest_error}.")
    binds = reader.read_accessor(document, binary, skin["inverseBindMatrices"])
    palette = []
    for name, values in zip(names, binds):
        inverse = Matrix(tuple(tuple(values[c*4+r] for c in range(4)) for r in range(4)))
        palette.append(ancestor @ captured_pose[name] @ inverse)
    points = []
    for item in document["meshes"]:
        for primitive in item["primitives"]:
            attrs = primitive["attributes"]
            decoded = {n: reader.read_accessor(document, binary, attrs[n]) for n in ("POSITION", "JOINTS_0", "WEIGHTS_0")}
            for point, joints, weights in zip(decoded["POSITION"], decoded["JOINTS_0"], decoded["WEIGHTS_0"]):
                p = sum(((palette[j] @ Vector(point))*w for j,w in zip(joints, weights) if w > 0), Vector((0, 0, 0)))
                points.append(tuple(AXES.inverted() @ p))
    return points, rest_error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=ROOT / "example/v2/modular/StytchDoll")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hidden-region", choices=("left-arm", "right-arm", "left-leg", "right-leg"))
    parser.add_argument("--hidden-regions", nargs="+", choices=("left-arm", "right-arm", "left-leg", "right-leg"))
    parser.add_argument("--no-render", action="store_true", help="Run all numerical replay gates without rendering PNGs.")
    parser.add_argument("--source-sha", default="local-uncommitted")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-attempt", default=None)
    args = parser.parse_args(argv if argv is not None else (sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []))
    hidden_regions = sorted(set((args.hidden_regions or [])+([args.hidden_region] if args.hidden_region else [])))
    output, fixture = args.output.resolve(), args.fixture.resolve(strict=True)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty replay output directory.")
    output.mkdir(parents=True, exist_ok=True)
    probe = NativePoseProbe.from_dict(strict_json_loads(args.pose.read_text("utf-8")))
    manifest = json.loads((fixture / "manifest.json").read_text("utf-8"))
    if probe.asset_sha256 != digest(fixture / "character.glb") or manifest["sha256"] != probe.asset_sha256:
        raise ValueError("Captured pose does not target this exact GLB fingerprint.")
    bpy.ops.wm.open_mainfile(filepath=str(fixture / "source.blend"), use_scripts=False)
    mesh, rig = bpy.data.objects["MeshvennScan"], bpy.data.objects["MeshvennCanonicalRig"]
    before = source_snapshot(mesh, rig)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.hide_render = obj is not mesh
    mesh.hide_set(False)
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    rig.data.pose_position = "POSE"
    bpy.context.view_layer.update()
    captured_rest = accumulated(probe, rest=True)
    native_rest_error = max(matrix_error(AXES @ rig.data.bones[name].matrix_local, rest) for name,rest in captured_rest.items())
    height_native = max(v.co.z for v in mesh.data.vertices)-min(v.co.z for v in mesh.data.vertices)
    assert native_rest_error/height_native < 2e-6
    rest = list(_positions((mesh,))[mesh.name])
    floor, height = min(p[2] for p in rest), max(p[2] for p in rest)-min(p[2] for p in rest)
    mesh.data.calc_loop_triangles()
    triangles = [tuple(t.vertices) for t in mesh.data.loop_triangles]
    center_x = (max(p[0] for p in rest)+min(p[0] for p in rest))/2
    torso = [.45 <= (p[2]-floor)/height <= .67 and abs(p[0]-center_x)/height <= .14 for p in rest]
    if not args.no_render:
        _camera((mesh,), 768, 32)
        _render(output / "native_rest.png")
    applied_error = apply_probe(rig, probe)
    native = list(_positions((mesh,))[mesh.name])
    if not args.no_render:
        _render(output / "native_pose.png")
    torso_edges = masked_edge_summary(rest, native, triangles, torso, height)
    assert source_snapshot(mesh, rig) == before
    reader = module("implementations.glb_export.modular_gltf")
    document, binary = reader.read_glb(fixture / "character.glb")
    raw, glb_rest_error = decoded_lbs(document, binary, probe, reader)
    raw_native_error = hausdorff(native, raw)
    meshes, rigs = _import(fixture / "character.glb")
    imported_error = apply_probe(rigs[0], probe)
    imported_by_mesh = _positions(meshes)
    imported = [p for mesh in meshes for p in imported_by_mesh[mesh.name]]
    if not args.no_render:
        _camera(meshes, 768, 32)
        _render(output / "glb_pose.png")
    for region in hidden_regions:
        hidden = next(obj for obj in meshes if obj.name == "Doll_"+region.replace("-", "_"))
        hidden.hide_render = True
    if hidden_regions and not args.no_render:
        _render(output / ("glb_pose_hidden_"+"_".join(hidden_regions)+".png"))
    import_raw_error = hausdorff(raw, imported)
    # Independently verify source skin, raw glTF LBS and Blender reimport. These
    # are diagnostic replay gates, not changes to existing export tolerances.
    passed = raw_native_error < 2e-5*height and import_raw_error < 2e-5*height
    report = {"passed": passed, "asset_sha256": probe.asset_sha256, "input_pose_sha256": digest(args.pose),
              "source_sha": args.source_sha, "run_id": args.run_id, "run_attempt": args.run_attempt,
              "hidden_region": hidden_regions[0] if len(hidden_regions) == 1 else None,
              "hidden_regions": hidden_regions,
              "coordinate_conversion": "Basis columns + Origin -> parent accumulation; A:(x,y,z)->(x,z,-y); D_native=A^-1 P_godot R_godot^-1 A; retain ancestor normalization once",
              "native_rest_error_in_heights": native_rest_error/height_native,
              "glb_rest_world_max_error": glb_rest_error, "native_applied_delta_error": applied_error,
              "imported_applied_delta_error": imported_error,
              "native_vs_decoded_glb_max_error_m": raw_native_error,
              "decoded_vs_reimport_max_error_m": import_raw_error,
              "torso_cohort": "frozen source rest Z/h in [0.45,0.67], abs lateral/h <= 0.14",
              "torso_edges": torso_edges, "source_authority_unchanged": True,
              "images": {p.name: digest(p) for p in output.glob("*.png")},
              "visual_qualification": False, "consumer_capture_pixel_equality_claimed": False,
              "scope": "Exact provided matrices only. No fabricated held/walk/hop snapshots; no consumer resource/code changes."}
    (output / "replay.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", "utf-8")
    assert passed, "Native source / decoded GLB / reimport pose replay disagreement."
    print(f"Native consumer pose replay PASS: source/raw {raw_native_error:.6g}m; raw/reimport {import_raw_error:.6g}m; torso quality remains unqualified.")


if __name__ == "__main__":
    main()
