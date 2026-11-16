"""Versioned evidence profile; regression passes never fill missing product evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import PROFILE_ID


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def implementation() -> dict:
    root = Path(__file__).resolve().parents[2]
    files = [*Path(__file__).resolve().parent.glob("*.py"), root / "scripts/qualify_diagnostic_evidence.py"]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}


def assemble_report(corpora: dict, *, attempt=None, comparison=None, reference=None, review=None) -> dict:
    regression_status = corpora.get("status", "unknown")
    if regression_status == "pass" and not corpora.get("all_full_matrices_passed", False):
        regression_status = "unknown"
    preservation = (comparison or {}).get("outside_pixels_status", "unknown")
    if (comparison or {}).get("reason") == "image_grid_changed":
        preservation = "fail"
    checks = [
        {"id": "frozen_regressions", "status": regression_status,
         "meaning": "Existing frozen diagnostic/planning/orchestration controls only."},
        {"id": "real_attempt_archive", "status": "pass" if attempt else "unknown",
         "meaning": "Verified before/after/provenance bytes; not provider fidelity."},
        {"id": "protected_pixels", "status": preservation,
         "meaning": "Exact source grid and pixels outside the independently authored edit mask."},
        {"id": "reference_glb_reload", "status": (reference or {}).get("status", "unknown"),
         "meaning": "Known reference geometry only; not an export of a corrected candidate."},
        {"id": "human_image_review", "status": (review or {}).get("human_review_status", "unknown"),
         "meaning": "Actual person's separately imported answers bound to exact evidence hashes."},
        {"id": "semantic_identity", "status": "unknown", "meaning": "A pixel score cannot certify identity."},
        {"id": "human_reviewed_generated_viewsets", "status": "unknown",
         "meaning": "A single archived edit does not qualify a reviewed generated multi-view population."},
        {"id": "corrected_glb_delivery", "status": "unknown",
         "meaning": "Requires D8/#85: accepted candidate, exact corrected export/reload and non-3D task review."},
    ]
    status = "fail" if any(c["status"] == "fail" for c in checks) else "unknown"
    report = {
        "schema_version": 1, "profile_id": PROFILE_ID, "qualification_status": status,
        "profile_basis": {"regression_thresholds": "Existing corpus policies and frozen expectations, unchanged.",
                          "protected_pixels": "D6 default outside_pixel_tolerance=0; no post-result relaxation.",
                          "pixel_alpha_threshold": .5,
                          "new_statistical_holdout": False,
                          "real_provider_numeric_metrics_are_descriptive": True},
        "checks": checks, "corpora": corpora, "attempt": attempt, "comparison": comparison,
        "reference": reference, "human_review": review or {"human_review_status": "unknown", "reason": "No human review imported."},
        "loop_promotion_status": "not_attempted",
        "implementation": implementation(),
        "limitations": ["Host-tool archive replay does not invoke a service or consume a native ImageGen quota.",
                        "Unknown provider cost/model/usage remain unknown; no zero-cost inference.",
                        "Exposed frozen cases are regression controls, not a new untouched statistical holdout.",
                        "The reference GLB is not reconstructed from the generated image.",
                        "D7/#84 and accessible corrected delivery #85 remain open."],
    }
    report["report_sha256"] = hashlib.sha256(canonical(report)).hexdigest()
    return report
