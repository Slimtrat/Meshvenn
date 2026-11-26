"""Compare an exact native source, raw GLB LBS and captured Godot GPU buffers.

No fitting, pose synthesis, skin edits or captures are performed. Reports contain
numeric evidence and input hashes; private app images/code/buffers stay external.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import importlib.util
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix
from mathutils.kdtree import KDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender import source
from scripts.cloth_lod import write_json
from scripts.cloth_replay_math import (
    AXES,
    MATRIX_LAYOUT,
    POSE_CONVENTION,
    accumulated,
    angles,
    coherence,
    lbs,
    matrix,
    oriented,
    summary,
    unit,
    verify_frames,
)

POLICY = {
    "native_vs_raw_max_error_in_heights": 2e-5,
    "raw_vs_gpu_max_error_in_heights": 2e-4,
    "raw_vs_gpu_max_normal_angle_deg": 0.02,
    "rest_frame_matrix_error": 2e-6,
    "applied_matrix_error": 2e-4,
    "scope": "Transport only. Recomputed geometric normals and directly skinned normals are distinct measurements. No contact, visual or gameplay acceptance.",
}
MAX_JSON_BYTES = 128 * 1024 * 1024


def read_json(path):
    def invalid(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("Capture exceeds the bounded replay input")
    return json.loads(data, parse_constant=invalid)


def capture_header(value, sha):
    if (
        value["SchemaId"] != "stytch.cloth-native-replay.v1"
        or value["AssetSha256"].lower() != sha
        or value["MatrixLayout"] != MATRIX_LAYOUT
        or value["PoseConvention"] != POSE_CONVENTION
    ):
        raise ValueError("Capture schema, asset or coordinate convention differs")


def rest_correspondence(mesh, points, joints, weights, names, triangles):
    native = np.array([tuple(mesh.matrix_world @ v.co) for v in mesh.data.vertices])
    native = (AXES[:3, :3] @ native.T).T
    tree = KDTree(len(native))
    for i, point in enumerate(native):
        tree.insert(point, i)
    tree.balance()
    rows = source.weights(mesh)
    mapping = []
    for point, js, ws in zip(points, joints, weights):
        hits = tree.find_range(point, 2e-6)
        if not hits:
            raise ValueError("Raw GLB vertex has no native rest-surface correspondence")
        target = {names[int(j)]: float(w) for j, w in zip(js, ws) if w > 1e-8}

        def difference(hit):
            row = rows[hit[1]]
            return max(
                abs(row.get(k, 0) - target.get(k, 0))
                for k in row.keys() | target.keys()
            )

        best = min(hits, key=difference)
        if difference(best) > 2e-6:
            raise ValueError("Coincident rest vertices disagree on native skin weights")
        mapping.append(best[1])
    mapping = np.array(mapping)
    mesh.data.calc_loop_triangles()
    if Counter(oriented(int(mapping[i]) for i in t) for t in triangles) != Counter(
        oriented(t.vertices) for t in mesh.data.loop_triangles
    ):
        raise ValueError(
            "Native/raw triangle multiplicity, tessellation or winding differs"
        )
    return mapping, float(np.ptp(native[:, 1]))


def evaluated_native(mesh):
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = evaluated.to_mesh()
    try:
        points = np.array([tuple(evaluated.matrix_world @ v.co) for v in data.vertices])
        normals = np.array([tuple(v.vector) for v in data.vertex_normals])
        normal_matrix = AXES[:3, :3] @ np.array(
            evaluated.matrix_world.to_3x3().inverted().transposed()
        )
        return (AXES[:3, :3] @ points.T).T, unit((normal_matrix @ normals.T).T)
    finally:
        evaluated.to_mesh_clear()


def apply_world_pose(rig, names, captured_rest, captured_pose):
    ai = np.linalg.inv(AXES)
    delta = ai @ captured_pose @ np.linalg.inv(captured_rest) @ AXES
    rig.data.pose_position = "POSE"
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()
    rig_world = np.array(rig.matrix_world)
    for i, name in enumerate(names):
        bone = rig.pose.bones[name]
        target = (
            np.linalg.inv(rig_world)
            @ delta[i]
            @ np.array(rig.matrix_world @ bone.bone.matrix_local)
        )
        bone.matrix = Matrix(target.tolist())
        bpy.context.view_layer.update()
    return float(
        max(
            np.max(
                abs(
                    np.array(rig.matrix_world @ rig.pose.bones[name].matrix)
                    @ np.linalg.inv(
                        np.array(rig.matrix_world @ rig.data.bones[name].matrix_local)
                    )
                    - delta[i]
                )
            )
            for i, name in enumerate(names)
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "asset", "capture", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args(
        argv if argv is not None else sys.argv[sys.argv.index("--") + 1 :]
    )
    original, asset, capture = (
        getattr(args, k).resolve(strict=True) for k in ("source", "asset", "capture")
    )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    asset_sha, original_sha = source.digest(asset), source.digest(original)
    write_json(output / "budget.json", POLICY)
    header = read_json(capture / "preview.json")
    if (
        header["SourceSha256"].lower() != asset_sha
        or header["ReplaySchema"] != "stytch.cloth-native-replay.v1"
    ):
        raise ValueError("Capture index targets a different source GLB")
    geometry_path = capture / "imported-geometry.json.gz"
    geometry_sha = source.digest(geometry_path)
    geometry = read_json(geometry_path)
    capture_header(geometry, asset_sha)
    if not geometry["CaptureCode"]["LoadedModuleVersionId"]:
        raise ValueError("Missing capture module identity")
    spec = importlib.util.spec_from_file_location(
        "cloth_glb_reader", ROOT / "implementations/glb_export/modular_gltf.py"
    )
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    document, binary = reader.read_glb(asset)
    if len(document.get("skins", [])) != 1 or len(document.get("meshes", [])) != 1:
        raise ValueError(
            "Exact-source audit requires one full-body reference mesh and skin"
        )
    skin = document["skins"][0]
    names = [document["nodes"][i]["name"] for i in skin["joints"]]
    if len(names) != 18 or len(set(names)) != 18:
        raise ValueError("Reference is not the eighteen-joint native cloth rig")
    node_parent = {
        c: i for i, n in enumerate(document["nodes"]) for c in n.get("children", [])
    }
    parents = [
        (
            skin["joints"].index(node_parent[i])
            if node_parent.get(i) in skin["joints"]
            else -1
        )
        for i in skin["joints"]
    ]
    captured_rest = accumulated(geometry["Bones"], names, parents, "Rest")
    raw_frames = source.glb_frames(asset)
    raw_rest = np.array([raw_frames[n] for n in names])
    rest_error = float(np.max(abs(raw_rest - captured_rest)))
    rest_global_error = float(
        np.max(
            abs(
                np.array([matrix(b["GlobalRest"]) for b in geometry["Bones"]])
                - captured_rest
            )
        )
    )
    if max(rest_error, rest_global_error) > POLICY["rest_frame_matrix_error"]:
        raise ValueError("Capture rests differ from raw native joint frames")
    binds = (
        np.array(reader.read_accessor(document, binary, skin["inverseBindMatrices"]))
        .reshape(-1, 4, 4)
        .transpose(0, 2, 1)
    )
    if [(b["Index"], b["Name"], b["Bone"]) for b in geometry["Binds"]] != [
        (i, name, i) for i, name in enumerate(names)
    ]:
        raise ValueError(
            "Captured skin bind slots differ from the raw joint-name table"
        )
    bind_error = float(
        np.max(
            abs(np.array([matrix(b["InverseBind"]) for b in geometry["Binds"]]) - binds)
        )
    )
    if bind_error > POLICY["rest_frame_matrix_error"]:
        raise ValueError("Captured inverse binds differ from the raw skin")
    primitive = document["meshes"][0]["primitives"][0]
    if len(document["meshes"][0]["primitives"]) != 1:
        raise ValueError("Reference must have one primitive")
    attrs = {
        k: np.array(reader.read_accessor(document, binary, v))
        for k, v in primitive["attributes"].items()
    }
    points, normals = attrs["POSITION"], attrs["NORMAL"]
    joints, weights = attrs["JOINTS_0"].astype(int), attrs["WEIGHTS_0"]
    triangles = np.array(
        reader.read_accessor(document, binary, primitive["indices"])
    ).reshape(-1, 3)
    if len(geometry["ImportedSurfaces"]) != 1:
        raise ValueError("Capture must retain the one raw primitive surface")
    imported = geometry["ImportedSurfaces"][0]
    if (
        imported["VertexCount"] != len(points)
        or not np.array_equal(
            np.array(imported["Indices"]).reshape(-1, 3), triangles[:, [0, 2, 1]]
        )
        or not np.array_equal(np.array(imported["BindIndices"]).reshape(-1, 4), joints)
    ):
        raise ValueError(
            "Imported vertex order, winding convention or bind slots differ"
        )
    imported_points, imported_normals = np.array(imported["Positions"]), np.array(
        imported["Normals"]
    )
    imported_weights = np.array(imported["Weights"]).reshape(-1, 4)
    rest_position_error = float(
        np.max(np.linalg.norm(imported_points - points, axis=1))
    )
    if (
        rest_position_error > 2e-6
        or np.max(abs(np.array(imported["Uv"]) - attrs["TEXCOORD_0"])) > 2e-6
    ):
        raise ValueError("Imported rest positions or UVs differ")
    mesh, rig = source.load(original)
    if rig is None or [b.name for b in rig.data.bones] != names:
        raise ValueError("Native source has a different armature")
    native_rest = np.array(
        [
            AXES @ np.array(rig.matrix_world @ rig.data.bones[n].matrix_local)
            for n in names
        ]
    )
    native_rest_error = float(np.max(abs(native_rest - captured_rest)))
    if native_rest_error > POLICY["rest_frame_matrix_error"]:
        raise ValueError("Native source rests differ from the capture")
    if [(b.parent.name if b.parent else None) for b in rig.data.bones] != [
        names[i] if i >= 0 else None for i in parents
    ]:
        raise ValueError("Native source hierarchy differs")
    mapping, height = rest_correspondence(
        mesh, points, joints, weights, names, triangles
    )
    arm_ids = [i for i, name in enumerate(names) if "arm" in name or "hand" in name]
    arm_mask = (
        np.sum(weights * np.isin(joints, arm_ids), axis=1)[triangles].mean(axis=1) > 0.5
    )
    report = {
        "schema_version": 1,
        "policy": POLICY,
        "asset_sha256": asset_sha,
        "source_blend_sha256": original_sha,
        "capture_geometry_sha256": geometry_sha,
        "engine": header["Engine"],
        "renderer": header["Renderer"],
        "height_m": height,
        "rest_frame_error": rest_error,
        "inverse_bind_error": bind_error,
        "native_rest_error": native_rest_error,
        "imported_rest_position_error_m": rest_position_error,
        "imported_weight_component_error": float(
            np.max(abs(imported_weights - weights))
        ),
        "rest_coherence": coherence(points, points, normals, triangles, arm_mask),
        "source_correspondence": "Rest positions plus complete joint-name weights and oriented triangle multiplicity; seam duplicates permitted",
        "index_convention": "Every imported triangle reverses raw glTF winding; comparisons use the verified raw convention",
        "native_normal_scope": "Blender evaluated vertex normals, recalculated from posed geometry; distinct from direct LBS normals and final normal-mapped pixels",
        "poses": [],
        "transport_passed": False,
        "visual_acceptance": False,
        "consumer_pixel_equality_claimed": False,
    }
    seen = set()
    for sample in header["ReplaySamples"]:
        path = (capture / sample["File"]).resolve(strict=True)
        if (
            not path.is_relative_to(capture)
            or path in seen
            or source.digest(path) != sample["Sha256"].lower()
        ):
            raise ValueError(
                "Capture index has an unsafe, duplicate or changed replay sample"
            )
        seen.add(path)
        pose = read_json(path)
        capture_header(pose, asset_sha)
        if (
            pose["ImportedGeometrySha256"].lower() != geometry_sha
            or pose["Mode"] != sample["Mode"]
            or pose["Frame"] != sample["Frame"]
            or pose["ImageSha256"].lower() != sample["ImageSha256"].lower()
        ):
            raise ValueError("Pose provenance contradicts the capture index")
        captured_pose = accumulated(pose["Bones"], names, parents, "Pose")
        if (
            np.max(
                abs(
                    captured_pose
                    - np.array([matrix(b["SkeletonSpace"]) for b in pose["Bones"]])
                )
            )
            > 2e-6
        ):
            raise ValueError("Composed local pose contradicts SkeletonSpace")
        relative = np.array(
            [
                np.linalg.inv(matrix(rest["Rest"])) @ matrix(p["Pose"])
                for rest, p in zip(geometry["Bones"], pose["Bones"])
            ]
        )
        if (
            np.max(
                abs(
                    relative
                    - np.array([matrix(b["RestRelative"]) for b in pose["Bones"]])
                )
            )
            > 2e-6
        ):
            raise ValueError(
                "RestRelative does not equal inverse(Rest) * complete local Pose"
            )
        palette = verify_frames(pose["Frames"]) @ captured_pose @ binds
        raw, raw_normal = lbs(palette, points, normals, joints, weights)
        imported_cpu, imported_cpu_normal = lbs(
            palette, imported_points, imported_normals, joints, imported_weights
        )
        if len(pose["NativeBakedSurfaces"]) != 1:
            raise ValueError("Unexpected GPU surface count")
        gpu = pose["NativeBakedSurfaces"][0]
        if gpu["VertexCount"] != len(points) or gpu["Indices"] != imported["Indices"]:
            raise ValueError("GPU bake changed the captured vertex/index order")
        gpu_points, gpu_normals = np.array(gpu["Positions"]), np.array(gpu["Normals"])
        applied_error = apply_world_pose(rig, names, captured_rest, captured_pose)
        native_points, native_normals = evaluated_native(mesh)
        a = summary(np.linalg.norm(native_points[mapping] - raw, axis=1))
        b = summary(np.linalg.norm(raw - gpu_points, axis=1))
        c = summary(angles(raw_normal, gpu_normals))
        passed = (
            a["max"] < height * POLICY["native_vs_raw_max_error_in_heights"]
            and b["max"] < height * POLICY["raw_vs_gpu_max_error_in_heights"]
            and c["max"] < POLICY["raw_vs_gpu_max_normal_angle_deg"]
            and applied_error < POLICY["applied_matrix_error"]
        )
        row = {
            "pose": path.name,
            "pose_sha256": source.digest(path),
            "mode": pose["Mode"],
            "frame": pose["Frame"],
            "native_vs_raw_m": a,
            "raw_vs_gpu_m": b,
            "raw_vs_gpu_normal_angle_deg": c,
            "imported_cpu_vs_gpu_m": summary(
                np.linalg.norm(imported_cpu - gpu_points, axis=1)
            ),
            "imported_cpu_vs_gpu_normal_angle_deg": summary(
                angles(imported_cpu_normal, gpu_normals)
            ),
            "native_geometric_vs_raw_skinned_normal_angle_deg": summary(
                angles(native_normals[mapping], raw_normal)
            ),
            "applied_matrix_error": applied_error,
            "raw_coherence": coherence(points, raw, raw_normal, triangles, arm_mask),
            "transport_passed": bool(passed),
        }
        report["poses"].append(row)
        write_json(output / "audit.json", report)
        print(
            f"{path.name}: source/raw {a['max']:.6g} m; raw/GPU {b['max']:.6g} m; transport {passed}",
            flush=True,
        )
    if not seen:
        raise ValueError("No captured pose samples")
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()
    if source.digest(original) != original_sha or source.digest(asset) != asset_sha:
        raise ValueError("Immutable audit input changed")
    report["transport_passed"] = all(row["transport_passed"] for row in report["poses"])
    write_json(output / "audit.json", report)
    if not report["transport_passed"]:
        raise ValueError("Captured transport failed; measurements retained")


if __name__ == "__main__":
    main()
