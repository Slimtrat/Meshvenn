"""Validate synchronized native matrices; project only authorized pose data."""
from __future__ import annotations

import math
import re

from .native_pose_probe import NativePoseProbe, matrix_rows

LAYOUT = "basis X column xyz, basis Y column xyz, basis Z column xyz, origin xyz; implicit last row 0 0 0 1"
CONVENTION = "Pose is the complete parent-local transform, not a rest-relative delta; RestRelative = inverse(Rest) * Pose"
REGIONS = frozenset(("body-core", "left-arm", "right-arm", "left-leg", "right-leg"))
MATRIX_TOLERANCE = 2e-4  # Captured float32 recomposition, not an export tolerance.
CONTEXT_KEYS = frozenset(("Consumer", "Pose", "Preset", "Sample", "ElapsedSeconds",
                          "CyclePhase", "AnatomyMask", "Lift", "Wobble", "WorldMode",
                          "BodyVariant", "InTransit"))


def multiply(a, b):
    return tuple(tuple(sum(a[r][i]*b[i][c] for i in range(4)) for c in range(4)) for r in range(4))


def error(a, b):
    return max(abs(x-y) for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def validate_matrix_proof(probe, proof):
    """Recompose redundant captured evidence; never treat full Pose as a delta."""
    if (not isinstance(proof, dict) or set(proof) != {"schema_version", "rest_relative", "skeleton_space", "ancestors"}
            or type(proof["schema_version"]) is not int or proof["schema_version"] != 1
            or not isinstance(proof["ancestors"], list) or not proof["ancestors"]):
        raise ValueError("Invalid captured matrix proof.")
    names = {b.name for b in probe.bones}
    if any(not isinstance(proof[key], dict) or set(proof[key]) != names
           for key in ("rest_relative", "skeleton_space")):
        raise ValueError("Redundant matrices must name every native joint exactly once.")
    accumulated, relative_error, skeleton_error = {}, 0.0, 0.0
    for bone in probe.ordered():
        relative_error = max(relative_error, error(multiply(bone.rest, matrix_rows(proof["rest_relative"][bone.name])), bone.pose))
        accumulated[bone.name] = multiply(accumulated[bone.parent], bone.pose) if bone.parent else bone.pose
        skeleton_error = max(skeleton_error, error(accumulated[bone.name], matrix_rows(proof["skeleton_space"][bone.name])))
    ancestors = []
    for item in proof["ancestors"]:
        if not isinstance(item, dict) or set(item) != {"Local", "World"}:
            raise ValueError("Ancestor proof contains only numeric local/world matrices.")
        ancestors.append((matrix_rows(item["Local"]), matrix_rows(item["World"])))
    ancestor_error = error(ancestors[-1][0], ancestors[-1][1])
    for child, parent in zip(ancestors, ancestors[1:]):
        ancestor_error = max(ancestor_error, error(child[1], multiply(parent[1], child[0])))
    errors = {"rest_relative_max_error": relative_error, "skeleton_space_max_error": skeleton_error,
              "ancestor_chain_max_error": ancestor_error}
    if max(errors.values()) > MATRIX_TOLERANCE:
        raise ValueError(f"Captured matrices do not recompose within float32 tolerance: {errors}.")
    return errors


def project_capture(value):
    """Whitelist matrices and minimal provenance, excluding private app content.

    Mount loadouts, semantic control implementation, ancestor node names and world
    telemetry are deliberately NOT carried into the public fixture.
    """
    if (not isinstance(value, dict) or type(value.get("SchemaVersion")) is not int
            or value["SchemaVersion"] != 1 or value.get("MatrixLayout") != LAYOUT
            or value.get("PoseConvention") != CONVENTION):
        raise ValueError("Unsupported synchronized capture schema or matrix conventions.")
    bones = value.get("Bones")
    if not isinstance(bones, list) or any(not isinstance(b, dict) or set(b) != {
            "Name", "Parent", "Rest", "Pose", "RestRelative", "SkeletonSpace"} for b in bones):
        raise ValueError("Incomplete captured native matrices.")
    document = {"AssetSha256": value.get("AssetSha256"), "CoordinateFrame": value.get("CoordinateFrame"),
                "Bones": [{key: b[key] for key in ("Name", "Parent", "Rest", "Pose")} for b in bones]}
    probe = NativePoseProbe.from_dict(document)
    ancestors = value.get("Ancestors")
    if not isinstance(ancestors, list) or any(not isinstance(a, dict) or not {"Local", "World"} <= a.keys() for a in ancestors):
        raise ValueError("Missing ancestor matrices.")
    proof = {"schema_version": 1, "rest_relative": {b["Name"]: b["RestRelative"] for b in bones},
             "skeleton_space": {b["Name"]: b["SkeletonSpace"] for b in bones},
             "ancestors": [{key: a[key] for key in ("Local", "World")} for a in ancestors]}
    errors = validate_matrix_proof(probe, proof)
    capture = value.get("CaptureFile")
    capture_sha = value.get("CaptureSha256")
    if (not isinstance(capture, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.png", capture)
            or not isinstance(capture_sha, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", capture_sha)):
        raise ValueError("Invalid synchronized PNG provenance.")
    regions = value.get("Regions")
    if (not isinstance(regions, list) or len(regions) != len(REGIONS)
            or any(not isinstance(r, dict) or set(r) != {"Id", "Visible"}
                   or not isinstance(r["Id"], str) or type(r["Visible"]) is not bool for r in regions)
            or {r["Id"] for r in regions} != REGIONS):
        raise ValueError("Invalid captured native region visibility.")
    context = value.get("Context")
    if not isinstance(context, dict) or not isinstance(context.get("Consumer"), str):
        raise ValueError("Missing capture consumer provenance.")
    selected = {k: v for k, v in context.items() if k in CONTEXT_KEYS}
    if any(type(v) not in (str, int, float, bool) or (type(v) is float and not math.isfinite(v)) for v in selected.values()):
        raise ValueError("Capture context must contain finite scalar provenance.")
    metadata = {"capture_filename": capture, "capture_sha256": capture_sha.lower(), "context": selected,
                "hidden_regions": sorted(r["Id"] for r in regions if not r["Visible"]),
                "matrix_recomposition": errors}
    return document, proof, metadata
