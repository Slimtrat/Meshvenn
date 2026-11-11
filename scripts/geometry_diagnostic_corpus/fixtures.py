"""Original analytic sources and expectations, frozen before native evaluation.

Uses the cardinal AABB recipe from the earlier corpus without changing it.
These authored silhouettes establish synthetic consistency truth, not topology.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.diagnostic_corpus.fixtures import (
    CAMERAS, canonical_json, png_bytes, raster_mask, rgba, sha256,
)
from . import CORPUS_VERSION, SCHEMA_VERSION

GENERATOR = "geometry-analytic-aabb-cardinal/1"
RASTERS = (64, 128)
# The three configurations separate raster sensitivity from voxel sensitivity.
CONFIGURATIONS = ((64, 32), (128, 32), (128, 48))
BOXES = (
    ("body", -.18, .18, -.14, .14, -.23, .15),
    ("head", -.14, .14, -.115, .115, .15, .37),
    ("left_arm", -.31, -.18, -.08, .08, -.12, .13),
    ("right_arm", .18, .285, -.08, .08, -.07, .13),
    ("left_leg", -.16, -.035, -.10, .10, -.42, -.23),
    ("right_leg", .035, .16, -.10, .10, -.42, -.23),
    ("identity_flag", .14, .205, -.06, .06, .30, .36),
    ("backpack", -.095, .095, .14, .235, -.10, .10),
    ("nose", -.05, .05, -.23, -.115, .22, .28),
)


@dataclass(frozen=True)
class Case:
    case_id: str
    split: str
    injection: str = "none"
    canonical: bool = False
    required: tuple[tuple[str, str], ...] = ()
    controls: tuple[str, ...] = ()


# Labels and defect parameters must be revised as a new corpus version, never
# changed to accommodate an observed heldout result.
CASES = (
    Case("healthy", "calibration", controls=("nonempty", "no_conflict", "no_blame")),
    Case("valid_informative_reduction", "calibration", "thin_depth",
         controls=("nonempty", "no_conflict", "no_blame", "large_valid_reduction")),
    Case("local_appendage_conflict", "calibration", "extend_front_arm",
         required=(("geometry.cross_view_conflict", "fail"), ("geometry.attribution", "unknown"))),
    Case("ambiguous_pair", "calibration", "pair_conflict",
         required=(("geometry.cross_view_conflict", "fail"), ("geometry.attribution", "unknown")),
         controls=("no_blame",)),
    Case("canonical_resolves_pair", "heldout", "pair_conflict", True,
         required=(("geometry.cross_view_conflict", "fail"),), controls=("canonical_eligible_front",)),
    Case("small_important_region", "heldout", "remove_front_flag",
         required=(("geometry.cross_view_conflict", "fail"),),
         controls=("important_region_failure", "good_mean_iou")),
    Case("intentional_asymmetry", "heldout", "authored_asymmetry", True,
         controls=("nonempty", "no_conflict", "no_blame")),
    Case("healthy_heldout", "heldout", "authored_variant",
         controls=("nonempty", "no_conflict", "no_blame")),
    Case("insufficient_coverage", "calibration", "single_view",
         required=(("coverage.insufficient", "unknown"),), controls=("no_blame",)),
    Case("empty_incompatible_views", "heldout", "disjoint_vertical",
         required=(("geometry.empty", "fail"),), controls=("empty", "no_blame")),
    Case("invalid_camera", "heldout", "perspective_front",
         required=(("camera.unsupported", "fail"),), controls=("no_blame",)),
    Case("real_worker_deadline", "calibration", "deadline",
         required=(("engine.time_budget", "unknown"),), controls=("no_blame",)),
    Case("real_native_rejection", "heldout", "native_invalid_resolution",
         controls=("native_rejection",)),
)


def boxes_for(case: Case) -> tuple:
    boxes = BOXES
    if case.injection == "thin_depth":
        boxes = tuple((label, x0, x1, -.015, .015, z0, z1)
                      for label, x0, x1, _y0, _y1, z0, z1 in boxes)
    if case.injection == "authored_asymmetry":
        boxes += (("intentional_left_fin", -.35, -.14, -.07, .07, .25, .39),)
    if case.injection == "authored_variant":
        boxes = tuple((label, x0 * .94, x1 * .94, y0 * 1.08, y1 * 1.08, z0, z1)
                      for label, x0, x1, y0, y1, z0, z1 in boxes)
    return boxes


def variant_for(case: Case, size: int) -> tuple[dict, dict[str, bytes]]:
    boxes, files, views = boxes_for(case), {}, []
    names = ("front",) if case.injection == "single_view" else tuple(CAMERAS)
    for name in names:
        angle = CAMERAS[name]
        observed_boxes = boxes
        if name == "front" and case.injection in ("extend_front_arm", "pair_conflict"):
            observed_boxes = tuple((label, x0, .43 if label == "right_arm" else x1, y0, y1, z0, z1)
                                   for label, x0, x1, y0, y1, z0, z1 in boxes)
        if name == "front" and case.injection == "remove_front_flag":
            observed_boxes = tuple(box for box in boxes if box[0] != "identity_flag")
        if case.injection == "disjoint_vertical":
            z0, z1 = ((.22, .42) if name in ("front", "right") else (-.42, -.22))
            observed_boxes = (("incompatible_valid_rectangle", -.20, .20, -.20, .20, z0, z1),)
        observed = raster_mask(observed_boxes, angle, size)
        reference = raster_mask(boxes, angle, size)
        assets = {}
        roles = [("image", rgba(observed)), ("mask", rgba(observed, color=(255, 255, 255)))]
        if case.canonical:
            roles.append(("reference", rgba(reference)))
        for role, pixels in roles:
            path = f"assets/{case.case_id}/{size}/{name}-{role}.png"
            data = png_bytes(size, pixels)
            files[path] = data
            assets[role] = {"path": path, "sha256": sha256(data), "width": size, "height": size,
                            "media_type": "image/png"}
        views.append({"view_id": name, "assets": assets, "declared_camera": {
            "projection": "perspective" if name == "front" and case.injection == "perspective_front" else "orthographic",
            "azimuth_degrees": angle, "elevation_degrees": 0, "verified": True},
            "analytic_camera": {"azimuth_degrees": angle, "elevation_degrees": 0},
            "occupied_pixels": sum(observed)})
    return {"raster_resolution": size, "views": views}, files


def build_corpus(destination: Path) -> dict:
    cases = []
    for spec in CASES:
        source = {"generator": GENERATOR, "boxes": boxes_for(spec),
                  "raster_coordinates": "bottom-left; u=x/(width-1), v=y/(height-1); inclusive edges",
                  "injection": spec.injection,
                  "truth_scope": "Exact authored silhouettes and injected defect; hidden surfaces/topology are unknown."}
        source_data = canonical_json(source)
        source_path = f"sources/{spec.case_id}.json"
        (destination / source_path).parent.mkdir(parents=True, exist_ok=True)
        (destination / source_path).write_bytes(source_data)
        variants = []
        for size in RASTERS:
            variant, files = variant_for(spec, size)
            variants.append(variant)
            for path, data in files.items():
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        regions = []
        if spec.injection == "remove_front_flag":
            regions = [{"view_id": "front", "label": "identity_flag", "bounds": [.64, .79, .72, .87]},
                       {"view_id": "back", "label": "identity_flag", "bounds": [.28, .79, .36, .87]}]
        cases.append({"case_id": spec.case_id, "split": spec.split, "injection": spec.injection,
                      "canonical": spec.canonical, "regions": regions,
                      "source": {"path": source_path, "sha256": sha256(source_data)},
                      "ground_truth": {"kind": "original_analytic_synthetic", "human_reviewed": False,
                         "known_faulty_observations": ["front"] if spec.injection in ("extend_front_arm", "pair_conflict", "remove_front_flag") else [],
                         "canonical_available_to_engine": spec.canonical,
                         "ambiguous_without_independent_canonical": spec.injection in ("extend_front_arm", "pair_conflict"),
                         "native_fault_kind": "real_dll_api_rejection" if spec.injection == "native_invalid_resolution" else
                            "real_worker_deadline_native_completion_unknown" if spec.injection == "deadline" else None},
                      "expected": {"required": [{"code": code, "status": status} for code, status in spec.required],
                                   "controls": spec.controls, "mean_iou_good_minimum": .90,
                                   "large_reduction_minimum": .90}, "variants": variants})
    manifest = {"schema_version": SCHEMA_VERSION, "corpus_version": CORPUS_VERSION, "generator": GENERATOR,
                "license": "GPL-3.0-or-later; original mathematical regression data under the existing repository license",
                "provenance": {"external_assets": [], "network_calls": 0, "provider_calls": 0, "paid_cost": 0,
                               "ai_generated": False, "ground_truth": "Exact analytic authorship, no human/generated-image approval"},
                "partition_policy": "Definitions, expectations and configuration grid frozen before first native evaluation. Heldout is never threshold fitting; reruns after fixes are regression evidence.",
                "execution_plan": {"configurations": [{"raster": raster, "voxel": voxel} for raster, voxel in CONFIGURATIONS],
                                   "permutation_configurations": [{"raster": 64, "voxel": 32}],
                                   "orders": ["canonical", "reverse", "rotate"], "max_seconds_per_analysis": 15.0,
                                   "operational_cases": "Only baseline canonical configuration; direct DLL rejection uses a hard-bounded subprocess."},
                "scope": {"D3": "Real NativeCore visual hull, voxel reprojection, leave-one-out, analytical controls only",
                          "D4_D8": "unknown", "D7": "initial tranche remains open", "issue_84": "open"}, "cases": cases}
    (destination / "manifest.json").write_bytes(canonical_json(manifest))
    return manifest
