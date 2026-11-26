"""Source-frame fidelity measurements; run Blender math in a bounded worker.

The versioned profile reports coarse benchmark gates, never semantic character,
important-part, rig or animation certification. No candidate-specific fitting.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILE = "native-cube-source-frame-fidelity-v1"
IOU_GATE_PROFILE = "per-view-min-v1"
CAMERAS = tuple((f"az{a:03d}", a, 0.) for a in (0, 45, 90, 135, 180, 225, 270, 315)) + (
    ("top", 0., -90.), ("bottom", 0., 90.))
# Frozen before the first candidate measurement; never reconstruction inputs.
WITHHELD_CAMERA_ANGLES = (30, 120, 210, 300)
ALL_CAMERAS = CAMERAS + tuple((f"withheld{a:03d}", a, 0.) for a in WITHHELD_CAMERA_ANGLES)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _checked(path, digest, maximum=64 * 1024 * 1024):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_size > maximum or not re.fullmatch(r"[a-f0-9]{64}", digest or ""):
        raise ValueError("Invalid bounded artifact record")
    if _sha(path) != digest:
        raise ValueError("Artifact SHA256 mismatch: " + str(path))
    return path


def _input_binding(asset, source_sha):
    """Return declared input IDs only after checking case, source and mask links."""
    names = ("input_evidence_path", "input_evidence_sha256", "reconstruction_manifest_path", "reconstruction_manifest_sha256")
    if not all(asset.get(n) for n in names):
        return None
    case_path = _checked(asset[names[0]], asset[names[1]])
    manifest_path = _checked(asset[names[2]], asset[names[3]])
    case = json.loads(case_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("complete") is not True or case not in manifest.get("cases", [])
            or case["glb"]["sha256"] != asset["glb_sha256"]
            or manifest["source"]["glb"]["sha256"] != source_sha):
        raise ValueError("Reconstruction input provenance mismatch")
    _checked(manifest_path.parent / case["glb"]["path"], asset["glb_sha256"])
    _checked(manifest_path.parent / manifest["source"]["glb"]["path"], source_sha)
    cameras = {c["id"]: c for c in manifest["cameras"]}
    allowed = {name: (a, e) for name, a, e in CAMERAS}
    ids = case["view_ids"]
    if not ids or len(set(ids)) != len(ids) or any(i not in allowed for i in ids):
        raise ValueError("Invalid source input camera profile")
    for name in ids:
        camera = cameras[name]
        if (camera["azimuth_degrees"], camera["elevation_degrees"]) != allowed[name] or camera["flip_x"] is not False:
            raise ValueError("Input camera does not match the frozen native profile")
        _checked(manifest_path.parent / camera["png"]["path"], camera["png"]["sha256"])
    return ids


def measure_fidelity(assets: list, output, blender_executable, *, raster_size=128, samples=4096, timeout_seconds=300):
    """Measure exact reloaded mesh JSONs, snapshotting SHA-bound mesh/GLB inputs.

    Each asset has asset_id, role, mesh_path, mesh_sha256, glb_path, glb_sha256,
    reload={verified:true,source_glb_sha256:...}. Exactly one role is source.
    Optional input_evidence_path/SHA and reconstruction_manifest_path/SHA bind
    input-view gates. Output must be new. Blender is trusted host configuration.
    """
    if type(raster_size) is not int or raster_size not in (128, 256):
        raise ValueError("Silhouette raster must be 128 or 256")
    if type(samples) is not int or not 128 <= samples <= 16384:
        raise ValueError("Surface sample count must be 128..16384")
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 600:
        raise ValueError("Worker deadline must be 1..600 seconds")
    if type(assets) is not list or not 2 <= len(assets) <= 16 or sum(a.get("role") == "source" for a in assets) != 1:
        raise ValueError("Exactly one source and 2..16 assets required")
    ids = [a.get("asset_id") for a in assets]
    if any(type(i) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", i) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Asset IDs must be safe and unique")
    source = next(a for a in assets if a["role"] == "source")
    source_frame = None
    checked = []
    for asset in assets:
        if asset.get("role") not in ("source", "candidate", "reference"):
            raise ValueError("Invalid asset role")
        mesh = _checked(asset["mesh_path"], asset["mesh_sha256"])
        glb = _checked(asset["glb_path"], asset["glb_sha256"])
        mesh_data = json.loads(mesh.read_text(encoding="utf-8"))
        frame = mesh_data.get("coordinate_frame")
        if (mesh_data.get("schema_version") != 1 or not isinstance(frame, str) or not frame
                or mesh_data.get("source_glb_sha256") != asset["glb_sha256"]):
            raise ValueError("Mesh lacks exact GLB/world-frame provenance")
        if source_frame is None:
            source_frame = frame
        elif source_frame != frame:
            raise ValueError("All mesh artifacts must declare the same world frame")
        reload = asset.get("reload", {})
        if reload.get("verified") is not True or reload.get("source_glb_sha256") != asset["glb_sha256"]:
            raise ValueError("Exact GLB reload provenance is required")
        checked.append(dict(asset, mesh_path=str(mesh), glb_path=str(glb),
            bound_input_view_ids=_input_binding(asset, source["glb_sha256"])))
    executable = Path(blender_executable).resolve(strict=True)
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    for asset in checked:
        for kind in ("mesh", "glb"):
            destination = out / (asset["asset_id"] + (".mesh.json" if kind == "mesh" else ".glb"))
            shutil.copyfile(asset[kind + "_path"], destination)
            _checked(destination, asset[kind + "_sha256"])
            asset[kind + "_path"] = str(destination)
    request = dict(schema_version=1, profile=PROFILE, assets=checked, output=str(out),
        raster_size=raster_size, samples=samples, worker_sha256=_sha(__file__))
    request_path = out / "fidelity-request.json"
    _write(request_path, request)
    command = [str(executable), "--background", "--factory-startup", "--python-exit-code", "1",
        "--python", str(Path(__file__).resolve()), "--", "--request", str(request_path)]
    with (out / "blender.stdout.log").open("wb") as stdout, (out / "blender.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=15)
            _write(out / "fidelity-failure.json", dict(status="timed_out", verification_status="unknown"))
            raise TimeoutError("Fidelity worker deadline exceeded; evidence retained")
    if code:
        raise RuntimeError("Fidelity Blender worker failed; inspect retained logs")
    result = json.loads((out / "fidelity.json").read_text(encoding="utf-8"))
    if result.get("request_sha256") != _sha(request_path) or result.get("status") != "completed":
        raise ValueError("Invalid fidelity worker receipt")
    return result


def _geometry(asset):
    from mathutils import Vector
    path = _checked(asset["mesh_path"], asset["mesh_sha256"])
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source_glb_sha256") != asset["glb_sha256"]:
        raise ValueError("Mesh JSON is bound to another GLB")
    vertices, triangles = data["vertices"], data["triangles"]
    if not 3 <= len(vertices) <= 500000 or not 1 <= len(triangles) <= 1000000:
        raise ValueError("Mesh geometry exceeds fidelity budget")
    if any(len(p) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10 for v in p) for p in vertices):
        raise ValueError("Mesh points must be finite in the declared native cube frame")
    if any(len(t) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in t) for t in triangles):
        raise ValueError("Invalid mesh triangle indices")
    return [Vector(p) for p in vertices], triangles


def _shared_frame(source_points):
    from mathutils import Vector
    low = Vector(tuple(min(p[a] for p in source_points) for a in range(3)))
    high = Vector(tuple(max(p[a] for p in source_points) for a in range(3)))
    longest = max(high - low)
    if longest <= 1e-9 or any(abs(c) > 1.000002 for p in source_points for c in p):
        raise ValueError("Source must be nondegenerate in the declared native cube")
    return (low + high) * .5, longest


def _triangles(points, faces, center, longest):
    return [tuple((points[i] - center) / longest for i in face) for face in faces]


def _surface(reference, candidate, samples):
    from scripts.glb_v2_surface_metrics import compare_surface_bvh, _surface_samples, _surface_tree, _surface_observations
    detail = compare_surface_bvh(reference, candidate, samples=samples)
    detail["distance_units"] = "fraction of SOURCE longest world-space bbox extent; common SOURCE center; no per-model fit"
    observations = [
        _surface_observations(_surface_samples(reference, samples, 2026), _surface_tree(candidate)),
        _surface_observations(_surface_samples(candidate, samples, 2026), _surface_tree(reference))]
    recall, precision = (sum(d <= .05 for d, _ in rows) / samples for rows in observations)
    detail["legacy_coarse"] = dict(distance_threshold=.05, precision=precision, recall=recall,
        fscore=2 * precision * recall / (precision + recall) if precision + recall else 0.)
    return detail


def _silhouettes(points, faces, size):
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from core.projection_frame import native_projection_axes
    from core.projection_math import compile_projection
    tree = BVHTree.FromPolygons(points, faces, all_triangles=True, epsilon=0.)
    masks = {}
    for name, azimuth, elevation in ALL_CAMERAS:
        right, up, direction = map(Vector, native_projection_axes(azimuth, elevation))
        transform = compile_projection(azimuth_degrees=azimuth, elevation_degrees=elevation)
        values = bytearray(size * size)
        for y in range(size):
            base = up * ((2 * (y + .5) / size - 1) * transform.vertical_extent) + direction * 20
            for x in range(size):
                origin = base + right * ((2 * (x + .5) / size - 1) * transform.horizontal_extent)
                values[y * size + x] = tree.ray_cast(origin, -direction, 40.)[0] is not None
        masks[name] = values
    return masks


def _iou(a, b):
    union = sum(bool(x or y) for x, y in zip(a, b))
    return sum(bool(x and y) for x, y in zip(a, b)) / union if union else 0.


def _gate(value, minimum, reason):
    return dict(status="unknown" if value is None else "pass" if value >= minimum else "fail",
        value=value, minimum=minimum, reason=reason)


def _worker(request_path):
    import bpy
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    if request["worker_sha256"] != _sha(__file__) or request["profile"] != PROFILE:
        raise ValueError("Fidelity worker changed after request")
    source = next(a for a in request["assets"] if a["role"] == "source")
    source_points, source_faces = _geometry(source)
    center, longest = _shared_frame(source_points)
    reference = _triangles(source_points, source_faces, center, longest)
    expected = _silhouettes(source_points, source_faces, request["raster_size"])
    result = dict(schema_version=1, profile=PROFILE, status="partial", verification_status="unknown",
        request_sha256=_sha(request_path), worker_sha256=request["worker_sha256"], blender_version=bpy.app.version_string,
        source=dict(asset_id=source["asset_id"], glb_sha256=source["glb_sha256"], mesh_sha256=source["mesh_sha256"]),
        shared_frame=dict(center=list(center), longest_extent=longest, candidate_fit=False),
        raster_size=request["raster_size"], cameras=[dict(id=n, azimuth_degrees=a, elevation_degrees=e) for n, a, e in ALL_CAMERAS],
        withheld_camera_angles=list(WITHHELD_CAMERA_ANGLES),
        threshold_authority="benchmark_glb_v2.py legacy .05/.60 coarse Fscore; IoU threshold .65 transferred from legacy MEAN to NEW stricter per-view-min-v1, frozen before measurements; not universal aesthetics",
        iou_gate_profile=IOU_GATE_PROFILE,
        limitations=["Area sampling cannot certify every thin important part.", "Input profile coverage is not complete surface visibility.",
            "No semantic, human, rig, animation or identity qualification.", "Distances at .005/.01/.02 are descriptive; no newly calibrated gate."], assets=[])
    for asset in request["assets"]:
        if asset["role"] == "source":
            continue
        points, faces = _geometry(asset)
        surface = _surface(reference, _triangles(points, faces, center, longest), request["samples"])
        actual = _silhouettes(points, faces, request["raster_size"])
        per_view = {name: _iou(expected[name], actual[name]) for name in expected}
        ids = asset["bound_input_view_ids"]
        source_iou = min(per_view[i] for i in ids) if ids else None
        withheld = [per_view[f"withheld{a:03d}"] for a in WITHHELD_CAMERA_ANGLES]
        target_iou = min(withheld)
        outside = sum(any(abs(c) > 1.000002 for c in p) for p in points)
        gates = dict(surface_fscore=_gate(surface["legacy_coarse"]["fscore"], .60, "Legacy coarse geometry threshold in common SOURCE frame."),
            source_iou=_gate(source_iou, .65, "NEW per-view-min-v1: minimum bound input-camera IoU, threshold transferred from legacy mean."),
            target_iou=_gate(target_iou if not outside else None, .65, "NEW per-view-min-v1: minimum four withheld camera IoUs. Outside cube makes raster incomplete."),
            important_parts=dict(status="unknown", reason="No complete validated local important-part comparison supplied."),
            coverage=dict(status="pass" if ids and len(ids) == 10 else "unknown", observed_input_view_ids=ids,
                reason="Declared and SHA-bound ten-camera INPUT profile only; no surface visibility certification."))
        if outside:
            gates["source_iou"] = _gate(None, .65, "Candidate extends outside the declared cube raster field.")
        result["assets"].append(dict(asset_id=asset["asset_id"], role=asset["role"],
            glb_sha256=asset["glb_sha256"], mesh_sha256=asset["mesh_sha256"], surface=surface,
            input_evidence_sha256=asset.get("input_evidence_sha256"), reconstruction_manifest_sha256=asset.get("reconstruction_manifest_sha256"),
            per_view_iou=per_view, mean_source_iou=sum(per_view[i] for i in ids)/len(ids) if ids else None,
            mean_target_iou=sum(withheld)/len(withheld), candidate_outside_cube_vertices=outside, gates=gates, verification_status="unknown"))
        _write(Path(request["output"]) / "fidelity.json", result)
    result["status"] = "completed"
    _write(Path(request["output"]) / "fidelity.json", result)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    _worker(args.request)
