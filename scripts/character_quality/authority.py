"""Source-authored spatial regions; no semantic labels invented for other assets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.diagnostic_qualification.reference import verify_fixture

ROOT = Path(__file__).resolve().parents[2]


def source_authority(source_glb_sha256: str) -> dict:
    fixture = ROOT / "tests/fixtures/diagnostics/provider-v1"
    verified = verify_fixture(fixture)
    frame = {"coordinate_frame": "Blender world/native normalized cube; no per-candidate fit",
             "source_glb_sha256": source_glb_sha256}
    frame_id = hashlib.sha256(json.dumps(frame, sort_keys=True).encode()).hexdigest()
    if source_glb_sha256 != verified["source_glb_sha256"]:
        return {"frame_id": frame_id, "regions": [], "sections": [], "authority_status": "unknown",
                "reason": "No source-validated semantic regions supplied for this asset."}
    proof = json.loads((fixture / "glb-reload-proof.json").read_bytes())
    evidence = verified["archived_reload_proof_sha256"]
    names = ("head", "body", "left_hand", "right_hand", "left_boot", "right_boot", "antenna_stem", "right_flag_pole")
    regions = [{"region_id": name, "bounds": [proof["before"][name]["minimum"], proof["before"][name]["maximum"]],
                "evidence_sha256": evidence, "validated": True} for name in names]
    # A whole stem box overlaps the head and tip. Probe the free middle of the
    # source-authored gap so their surfaces cannot stand in for the thin stem.
    stem, head, tip = (proof["before"][name] for name in ("antenna_stem", "head", "antenna_tip"))
    low, high = max(stem["minimum"][2], head["maximum"][2]), min(stem["maximum"][2], tip["minimum"][2])
    if high > low:
        mid, quarter = (low + high) / 2, (high - low) / 4
        bounds = [[*stem["minimum"][:2], mid - quarter], [*stem["maximum"][:2], mid + quarter]]
        definition = {"source_proof_sha256": evidence, "region_id": "antenna_free_stem", "bounds": bounds,
                      "rule": "Middle half of the source-only gap between the head and antenna tip, intersected with the original stem bounds."}
        authority = hashlib.sha256(json.dumps(definition, sort_keys=True, allow_nan=False).encode()).hexdigest()
        regions.append({"region_id": "antenna_free_stem", "bounds": bounds, "evidence_sha256": authority, "validated": True})
    else:
        definition = None
    sections = [{"section_id": name + "_mid", "normal": [0., 0., 1.],
                 "offset": sum(proof["before"][name][key][2] for key in ("minimum", "maximum")) / 2}
                for name in ("head", "body")]
    return {"frame_id": frame_id, "regions": regions, "sections": sections,
            "authority_status": "source_authored", "source_glb_sha256": source_glb_sha256,
            "evidence_sha256": evidence,
            "source_only_thin_probe": definition,
            "meaning": "Spatial bounds from the frozen original GLB import proof; not a human identity certificate."}
