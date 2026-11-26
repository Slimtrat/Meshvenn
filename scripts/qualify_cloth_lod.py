"""Source/LOD fidelity under exact captures and separate native joint probes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender import source
from meshvenn_humanoid.blender.probes import rotated_bone, evaluated_positions
from meshvenn_humanoid.blender.evaluation import make_regions, measure
from meshvenn_humanoid.models import LIMITS
from scripts.audit_cloth_replay import read_json, capture_header
from scripts.cloth_lod import (
    POLICY,
    REFERENCE_SHA256,
    SOURCE_SHA256,
    sampled_distance,
    surface,
    write_json,
)
from scripts.cloth_replay_math import AXES, accumulated, matrix


def measured_surfaces(path, capture, captured_rest, names, parents):
    mesh, rig = source.load(path)
    points, triangles = surface(mesh)
    native_rest = np.array(
        [
            AXES @ np.array(rig.matrix_world @ rig.data.bones[n].matrix_local)
            for n in names
        ]
    )
    if np.max(abs(native_rest - captured_rest)) > 2e-6:
        raise ValueError("Source/LOD native rests differ from this exact capture")
    result = {"rest": (points, triangles)}
    rows = source.weights(mesh)
    weights = np.array([[row.get(n, 0) for n in names] for row in rows])
    gltf_points = (AXES[:3, :3] @ np.array(points).T).T
    ph = np.column_stack((gltf_points, np.ones(len(points))))
    for sample in read_json(capture / "preview.json")["ReplaySamples"]:
        pose_path = (capture / sample["File"]).resolve(strict=True)
        if (
            not pose_path.is_relative_to(capture)
            or source.digest(pose_path) != sample["Sha256"].lower()
        ):
            raise ValueError("Captured sample changed or escaped its root")
        pose = read_json(pose_path)
        capture_header(pose, REFERENCE_SHA256)
        pose_global = accumulated(pose["Bones"], names, parents, "Pose")
        palette = pose_global @ np.linalg.inv(captured_rest)
        blend = np.einsum("nk,kij->nij", weights, palette)
        posed = np.einsum("nij,nj->ni", blend, ph)[:, :3]
        native = (AXES[:3, :3].T @ posed.T).T
        result[pose_path.name] = (native.tolist(), triangles)
    # These probes are explicitly native producer probes, not fabricated Walk,
    # equipment, contact or actual consumer-target captures.
    for side in ("L", "R"):
        for joint, degrees, axis in (
            ("forearm", 45, (0, 1, 0)),
            ("forearm", 90, (0, 1, 0)),
            ("upper_arm", 45, (0, 1, 0)),
            ("upper_arm", 70, (0, 1, 0)),
            ("hand", 45, (0, 1, 0)),
            ("thigh", 45, (1, 0, 0)),
            ("shin", 90, (1, 0, 0)),
            ("foot", 30, (1, 0, 0)),
        ):
            angle = degrees if side == "L" else -degrees
            with rotated_bone(rig, joint + "." + side, angle, axis, world_space=True):
                result[f"native-{joint}-{side}-{degrees}"] = (
                    evaluated_positions(mesh),
                    triangles,
                )
    native_values, evidence = measure(mesh, rig, make_regions(mesh, rig, points))
    saved_lod = json.loads(mesh.get("meshvenn_cloth_lod", "{}"))
    evidence["inherited_protection_vertices"] = saved_lod.get("policy", {}).get(
        "feedback_source_vertices", []
    )
    return result, native_values, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "candidate", "capture", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args(
        argv if argv is not None else sys.argv[sys.argv.index("--") + 1 :]
    )
    original, candidate, capture = (
        getattr(args, k).resolve(strict=True)
        for k in ("source", "candidate", "capture")
    )
    original_sha, candidate_sha = source.digest(original), source.digest(candidate)
    if original_sha != SOURCE_SHA256:
        raise ValueError(
            "Fidelity reference must be the pinned full-resolution native source"
        )
    output = args.output.resolve()
    output.mkdir(exist_ok=False, parents=True)
    budget = {
        "max_sampled_surface_error_m": POLICY["max_sampled_surface_error_m"],
        "p99_sampled_surface_error_m": POLICY["p99_sampled_surface_error_m"],
        "native_limits": LIMITS,
        "scope": "Same pre-existing source/LOD surface budgets applied to every rest/posed sample. No visual/consumer admission. Capture completeness is separately required.",
    }
    write_json(output / "budget.json", budget)
    geo = read_json(capture / "imported-geometry.json.gz")
    capture_header(geo, REFERENCE_SHA256)
    names = [b["Name"] for b in geo["Bones"]]
    parents = [b["Parent"] for b in geo["Bones"]]
    rest = accumulated(geo["Bones"], names, parents, "Rest")
    reference, original_native, _ = measured_surfaces(
        original, capture, rest, names, parents
    )
    current, candidate_native, evidence = measured_surfaces(
        candidate, capture, rest, names, parents
    )
    if reference.keys() != current.keys():
        raise ValueError("Incomplete source/LOD pose comparison")
    native_failures = {
        k: v
        for k, v in candidate_native.items()
        if (v > LIMITS[k][1] if LIMITS[k][0] == "max" else v < LIMITS[k][1])
    }
    report = {
        "schema_version": 1,
        "source_sha256": original_sha,
        "candidate_sha256": candidate_sha,
        "reference_glb_sha256": REFERENCE_SHA256,
        "budget": budget,
        "source_native_profile": original_native,
        "candidate_native_profile": candidate_native,
        "failed_candidate_native_checks": native_failures,
        "candidate_native_evidence": evidence,
        "poses": [],
        "feedback_source_vertices": evidence["inherited_protection_vertices"],
        "fidelity_passed": False,
        "selected": False,
        "visual_acceptance": False,
        "consumer_admission": False,
        "missing_consumer_cases": [
            "walk",
            "leg",
            "missing-region",
            "equipment",
            "contact",
        ],
        "scope": "Finite bidirectional samples of source versus LOD triangles, not continuous Hausdorff/silhouette proof. Preserves existing source defects; does not certify anatomical quality.",
    }
    for label in reference:
        error = sampled_distance(
            reference[label],
            current[label],
            protect_above=0.8 * budget["max_sampled_surface_error_m"],
        )
        feedback_vertices = error.pop("feedback_source_vertices")
        passed = (
            error["max"] <= budget["max_sampled_surface_error_m"]
            and error["p99"] <= budget["p99_sampled_surface_error_m"]
        )
        row = {
            "pose": label,
            "sampled_surface_distance_m": error,
            "passed": passed,
            "feedback_source_vertices": feedback_vertices if not passed else [],
        }
        report["poses"].append(row)
        report["feedback_source_vertices"] = sorted(
            set(evidence["inherited_protection_vertices"])
            | {i for r in report["poses"] for i in r["feedback_source_vertices"]}
        )
        write_json(output / "fidelity.json", report)
        print(label, json.dumps(error), passed, flush=True)
    report["fidelity_passed"] = not native_failures and all(
        r["passed"] for r in report["poses"]
    )
    write_json(output / "fidelity.json", report)
    if (
        source.digest(original) != original_sha
        or source.digest(candidate) != candidate_sha
    ):
        raise ValueError("Immutable fidelity input changed")
    if not report["fidelity_passed"]:
        raise ValueError(
            "LOD failed a frozen fidelity budget; keep measurements and do not select it"
        )


if __name__ == "__main__":
    main()
