"""Archive measured records and representative original artifacts, without rerendering."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.diagnostic_corpus.fixtures import canonical_json, sha256
from .runner import checked_path


def compact_run(summary_path: Path, *, label: str, limitations=()) -> dict:
    encoded = summary_path.read_bytes()
    summary = json.loads(encoded)
    records = []
    for record in summary["records"]:
        data = {key: record[key] for key in ("case_id", "split", "raster_resolution", "voxel_resolution", "order",
                                             "elapsed_seconds", "score")}
        data.update({key: record[key] for key in ("policy", "policy_sha256", "occupied_count", "engine_provenance",
                                                   "native_probe", "native_worker_probe", "execution_failure") if key in record})
        data["findings"] = [{key: finding[key] for key in ("code", "status", "view_ids", "regions", "reason")}
                            for finding in record.get("report", {}).get("findings", [])]
        data["native_experiments"] = [{"experiment_id": experiment["experiment_id"], "state": experiment["state"],
            "excluded_view_ids": experiment["excluded_view_ids"], "included_view_ids": experiment["included_view_ids"],
            "elapsed_seconds": experiment["elapsed_seconds"], "volume": experiment["volume"]}
            for experiment in record.get("experiments", [])]
        data["trace"] = record.get("trace", [])
        data["artifact_count"] = len(record.get("artifacts", []))
        data["artifact_manifest_sha256"] = sha256(canonical_json(record.get("artifacts", [])))
        data["regional_measurements"] = [{"view_id": view["view_id"], "iou": view["metrics"]["iou"],
            "important_regions": view["metrics"]["important_regions"]} for view in record.get("views", [])]
        data["direct_pair_measurements"] = [{"target_view_id": pair["target_view_id"], "counterpart_view_id": pair["counterpart_view_id"],
            "mapping": pair["mapping"], "iou": pair["metrics"]["iou"], "important_regions": pair["metrics"]["important_regions"],
            "raster_tolerance_pixels": pair["raster_tolerance_pixels"]} for pair in record.get("pair_comparisons", [])]
        records.append(data)
    return {"label": label, "source_qualification_sha256": sha256(encoded),
            "manifest_sha256": summary["manifest_sha256"], "qualification_identity": summary["qualification_identity"],
            "qualification_status": summary["qualification_status"], "complete_matrix": summary["complete_matrix"],
            "authorities_unchanged": summary["authorities_unchanged"], "implementation": summary["implementation"],
            "metrics": summary["metrics"], "order_checks": summary["order_checks"],
            "resolution_sensitivity": summary["resolution_sensitivity"], "elapsed_seconds": summary["elapsed_seconds"],
            "network_calls": summary["network_calls"], "provider_calls": summary["provider_calls"],
            "paid_cost": summary["paid_cost"], "limitations": list(limitations), "records": records}


def export_record(summary_path: Path, destination: Path, *, label: str, limitations=(), examples=()) -> dict:
    """Append a measured attempt; existing attempt labels cannot be overwritten."""
    record_path = destination / "geometry-diagnostic-corpus-baseline.json"
    document = json.loads(record_path.read_bytes()) if record_path.exists() else {
        "schema_version": 1, "scope": "Synthetic analytic native D3 evidence; no full product acceptance", "runs": []}
    if any(run["label"] == label for run in document["runs"]):
        raise ValueError("A development record label already exists; prior failures cannot be overwritten")
    compact = compact_run(summary_path, label=label, limitations=limitations)
    document["runs"].append(compact)
    summary = json.loads(summary_path.read_bytes())
    output_root = summary_path.parent
    evidence = []
    for name, case_id, raster, voxel in examples:
        item = next(record for record in summary["records"] if record["case_id"] == case_id and
                    record["raster_resolution"] == raster and record["voxel_resolution"] == voxel and record["order"] == "canonical")
        source = checked_path(output_root, item["path"])
        target = destination / "geometry-diagnostic-corpus-evidence" / name
        target.mkdir(parents=True, exist_ok=False)
        for artifact in item.get("artifacts", []):
            original = checked_path(source, artifact["path"])
            if sha256(original.read_bytes()) != artifact["sha256"]:
                raise ValueError("Measured artifact changed before archival")
            shutil.copyfile(original, target / original.name)
        for filename in ("diagnostic-report.json", "observation.json", "analytic-source.json"):
            original = source / filename
            if original.exists():
                shutil.copyfile(original, target / filename)
        report = target / "diagnostic-report.json"
        evidence.append({"name": name, "case_id": case_id, "raster_resolution": raster, "voxel_resolution": voxel,
                         "report_path": f"geometry-diagnostic-corpus-evidence/{name}/diagnostic-report.json" if report.exists() else None,
                         "report_sha256": sha256(report.read_bytes()) if report.exists() else None,
                         "observation_sha256": sha256((target / "observation.json").read_bytes())})
    compact["committed_examples"] = evidence
    destination.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(canonical_json(document))
    return compact
