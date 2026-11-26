"""Bind exported geometry measurements to plain-language review observations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.diagnostic_qualification.integrity import checked_path, read_json, verify_file
from .authority import source_authority
from .delivery import inspect_delivery
from .metrics import mesh_quality
from .profile import compare_quality


def assess_rendered(render_manifest: dict, *, fidelity=None) -> dict:
    root = Path(render_manifest["output_root"])
    assets = render_manifest["assets"]
    sources = [a for a in assets if a["role"] == "source"]
    if len(sources) != 1 or render_manifest.get("status") != "completed":
        raise ValueError("Character assessment requires one source and complete renders.")
    source = sources[0]
    observed = {}
    if fidelity is not None:
        if (fidelity.get("status") != "completed" or fidelity.get("source", {}).get("glb_sha256") != source["glb"]["sha256"]
                or fidelity.get("source", {}).get("mesh_sha256") != source["mesh"]["sha256"]
                or fidelity.get("shared_frame", {}).get("candidate_fit") is not False):
            raise ValueError("Fidelity evidence is incomplete, fitted or bound to another source.")
        rows = fidelity["assets"]
        observed = {row["asset_id"]: row for row in rows}
        if len(observed) != len(rows) or set(observed) != {a["asset_id"] for a in assets if a["role"] == "candidate"}:
            raise ValueError("Fidelity evidence omits or duplicates a reviewed candidate.")
        for asset in assets:
            row = observed.get(asset["asset_id"])
            if row is not None and (row.get("glb_sha256") != asset["glb"]["sha256"] or row.get("mesh_sha256") != asset["mesh"]["sha256"]):
                raise ValueError("Surface fidelity refers to a stale reviewed GLB.")
    authority = source_authority(source["glb"]["sha256"])
    measurements, deliveries = {}, {}
    for asset in assets:
        for record in (asset["glb"], asset["mesh"]):
            if verify_file(root, record)["status"] != "pass":
                raise ValueError("Reviewed geometry artifact changed: " + asset["asset_id"])
        receipt = asset["reload"]
        if receipt.get("verified") is not True or receipt.get("source_glb_sha256") != asset["glb"]["sha256"]:
            raise ValueError("Character reload receipt refers to another GLB.")
        path = checked_path(root, asset["glb"]["path"])
        deliveries[asset["asset_id"]] = inspect_delivery(path, asset["glb"]["sha256"])
        mesh = read_json(checked_path(root, asset["mesh"]["path"]))
        if mesh.get("source_glb_sha256") != asset["glb"]["sha256"]:
            raise ValueError("Measured vertices do not belong to the reviewed GLB.")
        measurements[asset["asset_id"]] = mesh_quality(mesh["vertices"], mesh["triangles"],
            frame_id=authority["frame_id"], regions=authority["regions"], sections=authority["sections"],
            source_glb_sha256=asset["glb"]["sha256"])
    candidates = []
    for asset in assets:
        if asset["role"] != "candidate":
            continue
        measured = measurements[asset["asset_id"]]
        row = observed.get(asset["asset_id"])
        gates = None
        if row is not None:
            digest = hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False).encode()).hexdigest()
            gates = {name: dict(gate, evidence_sha256=digest) for name, gate in row.get("gates", {}).items()}
        comparison = compare_quality(measurements[source["asset_id"]], measured, preservation_gates=gates)
        missing = [r["region_id"] for r in comparison["regions"] if r["surface_presence_status"] == "fail"]
        if missing:
            # Presence is a spatial observation, not inferred semantic identity.
            evidence = hashlib.sha256(json.dumps(comparison["regions"], sort_keys=True, allow_nan=False).encode()).hexdigest()
            gates = dict(gates or {}, important_parts={"status": "fail", "evidence_sha256": evidence,
                         "reason": "No surface measured in some source-authored spatial regions: " + ", ".join(missing)})
            comparison = compare_quality(measurements[source["asset_id"]], measured, preservation_gates=gates)
        warnings = []
        names = {"head": "tête", "body": "buste", "left_hand": "main gauche", "right_hand": "main droite",
                 "left_boot": "pied gauche", "right_boot": "pied droit", "antenna_stem": "tige de l’antenne",
                 "antenna_free_stem": "partie libre de l’antenne", "right_flag_pole": "perche du drapeau"}
        angular = [names.get(r["region_id"], r["region_id"]) for r in comparison["regions"] if r["shape_status"] == "fail"]
        if comparison["shape_status"] == "fail":
            warnings.append("Des formes sont plus anguleuses que la référence selon le profil de contrôle.")
        if angular:
            warnings.append("Zones plus anguleuses mesurées : " + ", ".join(angular) + ".")
        elif comparison["shape_status"] == "unknown":
            warnings.append("Les mesures de forme sont incomplètes ou mitigées : comparez la tête et le buste.")
        for region in missing:
            warnings.append("Aucune surface mesurée dans la zone de référence : " + names.get(region, region) + ". Une pièce peut être déplacée ou perdue.")
        if comparison["preservation_status"] == "unknown":
            warnings.append("La fidélité complète et la préservation des détails restent à vérifier.")
        if comparison["preservation_status"] == "fail" and not missing:
            warnings.append("Au moins un contrôle de fidélité ne passe pas : inspectez le résultat.")
        candidates.append({"asset_id": asset["asset_id"], "label": asset["label"],
            "glb_sha256": asset["glb"]["sha256"], "mesh_sha256": asset["mesh"]["sha256"],
            "measurements": measured, "delivery": deliveries[asset["asset_id"]],
            "comparison": comparison, "fidelity": row, "warnings": warnings,
            "quality_certification": "unknown", "human_review": "unknown"})
    return {"schema_version": 1, "profile_id": "character-shape-review-v1", "source_authority": authority,
            "render_request_sha256": render_manifest["request_sha256"], "source_glb_sha256": source["glb"]["sha256"],
            "source_measurements": measurements[source["asset_id"]], "source_delivery": deliveries[source["asset_id"]],
            "candidates": candidates, "quality_certification": "unknown", "human_review": "unknown",
            "limitation": "Analytic reference-relative shape observations and coarse geometry checks do not certify aesthetics, identity or animation."}
