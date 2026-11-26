"""Reconstruct, reload and compare actual exported characters in one audited run."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import time

from scripts.diagnostic_qualification.integrity import checked_path, file_record, inventory_tree, read_json, sha256_file, verify_file
from .assessment import assess_rendered
from .delivery import inspect_delivery
from .fidelity import measure_fidelity
from .presentation import write_presentation
from .render import render_comparison

ROOT = Path(__file__).resolve().parents[2]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _audit_reconstruction(path):
    path = Path(path).resolve(strict=True)
    root, manifest = path.parent, read_json(path)
    if (manifest.get("schema_version") != 1 or manifest.get("complete") is not True
            or type(manifest.get("cases")) is not list or not 1 <= len(manifest["cases"]) <= 16):
        raise ValueError("Reconstruction evidence is incomplete.")
    for case in manifest["cases"]:
        if type(case.get("id")) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case["id"]):
            raise ValueError("Reconstruction case ID must be a safe identifier.")
    original = manifest["source"]
    if (original.get("role") != "source" or original.get("original_sha256") != original["glb"]["sha256"]
            or original["reload"].get("source_glb_sha256") != original["glb"]["sha256"]
            or original["reload"].get("verified") is not True):
        raise ValueError("Original GLB provenance is not bound to the reconstruction source.")
    records = [manifest["source"]["glb"], manifest["source"]["hero"]]
    records += [c["glb"] for c in manifest["cases"]] + [c["hero"] for c in manifest["cases"]]
    records += [v["png"] for v in manifest["cameras"]]
    if len({c["id"] for c in manifest["cases"]}) != len(manifest["cases"]):
        raise ValueError("Duplicate reconstruction cases.")
    for record in records:
        if verify_file(root, record)["status"] != "pass":
            raise ValueError("Reconstruction artifact changed: " + record["path"])
    for case in manifest["cases"]:
        receipt = case["reload"]
        if receipt.get("verified") is not True or receipt.get("source_glb_sha256") != case["glb"]["sha256"]:
            raise ValueError("Reconstruction export was not reloaded as the exact file.")
        if case["canonical_transform"].get("per_case_fit") is not False:
            raise ValueError("Independent candidate fitting cannot qualify fidelity.")
    return root, manifest


def _reconstruct(blender, native_library, output, *, resolution, mask_size, view_counts, source_glb=None):
    command = [str(blender), "--background", "--factory-startup", "--python-exit-code", "1", "--python",
               str(ROOT / "scripts/character_quality/reconstruct.py"), "--", "--output", str(output),
               "--native-library", str(native_library), "--resolution", str(resolution), "--mask-size", str(mask_size),
               "--view-counts", *map(str, view_counts), "--hero-size", "640"]
    if source_glb:
        command += ["--source-glb", str(source_glb)]
    with output.with_suffix(".stdout.log").open("wb") as out, output.with_suffix(".stderr.log").open("wb") as err:
        process = subprocess.Popen(command, stdout=out, stderr=err)
        try:
            code = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
            raise ValueError("Character reconstruction exceeded its bounded worker timeout.")
    if code:
        raise ValueError("Character reconstruction failed; original worker logs are retained.")
    return output / "manifest.json"


def qualify_characters(output, *, blender_executable, native_library=None, source_glb=None,
                       from_reconstruction=(), include_high_resolution=True, include_dense_views=True, render_size=640):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    stages = []
    try:
        blender = Path(blender_executable).resolve(strict=True)
        paths = [Path(p) for p in from_reconstruction]
        if not paths:
            if native_library is None:
                raise ValueError("A native library is required for actual reconstruction.")
            native = Path(native_library).resolve(strict=True)
            paths.append(_reconstruct(blender, native, output / "reconstruction-64", resolution=64,
                         mask_size=256, view_counts=(2, 8, 10), source_glb=source_glb))
            if include_high_resolution:
                paths.append(_reconstruct(blender, native, output / "reconstruction-128", resolution=128,
                             mask_size=512, view_counts=(10,18) if include_dense_views else (10,), source_glb=source_glb))
        audited = [_audit_reconstruction(path) for path in paths]
        first_root, first = audited[0]
        source = first["source"]
        source_sha = source["glb"]["sha256"]
        if source_glb is not None:
            explicit_source = Path(source_glb).resolve(strict=True)
            if sha256_file(explicit_source) != source_sha:
                raise ValueError("The explicitly requested source GLB differs from the compared cached source.")
        assets = [{"asset_id": "source", "role": "source", "label": "Référence originale à conserver",
                   "glb_path": str(checked_path(first_root, source["glb"]["path"])), "glb_sha256": source_sha}]
        inputs = {}
        for path, (root, manifest) in zip(paths, audited):
            if manifest["source"]["glb"]["sha256"] != source_sha:
                raise ValueError("The compared reconstructions do not share one original source.")
            for case in manifest["cases"]:
                asset_id = "r" + str(case["resolution"]) + "_" + case["id"]
                if asset_id in inputs:
                    raise ValueError("Duplicate resolution/view/refinement candidate.")
                angles = len(case["view_ids"])
                finish = "finition Organic" if case["surface_refinement"] == "organic" else "sans finition"
                label = f"{angles} angles — {finish} — " + ("maillage fin" if case["resolution"] >= 128 else "maillage standard")
                assets.append({"asset_id": asset_id, "role": "candidate", "label": label,
                    "glb_path": str(checked_path(root, case["glb"]["path"])), "glb_sha256": case["glb"]["sha256"]})
                raw = root / (case["id"] + ".json")
                if read_json(raw) != case:
                    raise ValueError("Candidate metadata differs from the original reconstruction record.")
                inputs[asset_id] = {"case_id": case["id"], "input_view_ids": case["view_ids"],
                    "input_evidence_path": str(raw), "input_evidence_sha256": file_record(raw, root)["sha256"],
                    "reconstruction_manifest_path": str(Path(path).resolve()),
                    "reconstruction_manifest_sha256": file_record(path, root)["sha256"]}
        stages.append("actual_reconstruction_artifacts_verified")
        render = render_comparison(assets, output / "review", blender_executable=blender,
                                   size=render_size, timeout_seconds=900)
        stages.append("actual_exported_glbs_reloaded_and_rendered")
        fidelity_assets = []
        for asset in render["assets"]:
            fidelity_assets.append({"asset_id": asset["asset_id"], "role": asset["role"],
                "mesh_path": str(checked_path(output / "review", asset["mesh"]["path"])),
                "glb_path": str(checked_path(output / "review", asset["glb"]["path"])),
                "mesh_sha256": asset["mesh"]["sha256"], "glb_sha256": asset["glb"]["sha256"],
                "reload": asset["reload"], **inputs.get(asset["asset_id"], {})})
        fidelity = measure_fidelity(fidelity_assets, output / "fidelity", blender, raster_size=128, samples=4096, timeout_seconds=600)
        stages.append("source_frame_surface_and_withheld_view_checks_completed")
        assessment = assess_rendered(render, fidelity=fidelity)
        write_json(output / "assessment.json", assessment)
        render["character_assessment"] = assessment
        write_json(output / "review/render-manifest.json", render)
        page = write_presentation(render, output / "review")
        result = {"schema_version": 1, "technical_status": "completed", "quality_certification": "unknown",
                  "elapsed_seconds": time.monotonic() - started, "stages": stages,
                  "source_glb_sha256": source_sha, "candidate_count": len(inputs),
                  "reconstruction_mode": "cached_byte_bound_glb_evidence" if from_reconstruction else "native_reconstruction_executed",
                  "review_page": file_record(page, output), "assessment": file_record(output / "assessment.json", output),
                  "render_manifest": file_record(output / "review/render-manifest.json", output),
                  "fidelity": file_record(output / "fidelity/fidelity.json", output),
                  "human_review": "unknown", "animated_use": "unknown"}
        write_json(output / "qualification.json", result)
        write_json(output / "inventory.json", inventory_tree(output))
        return result
    except Exception as exc:
        write_json(output / "qualification.json", {"schema_version": 1, "technical_status": "failed",
            "quality_certification": "unknown", "elapsed_seconds": time.monotonic() - started,
            "stages": stages, "error": {"type": type(exc).__name__, "message": str(exc)}})
        raise
