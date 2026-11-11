"""Analytically authored fixtures; no Blender, downloads, or model calls.

The source is a union of axis-aligned boxes. At the declared cardinal cameras
each orthographic projection is exactly a union of rectangles. Raster samples
use the engine's bottom-left coordinates, u=x/(width-1), v=y/(height-1).
This establishes synthetic truth, not evidence about real/generated photographs.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct
import zlib

from . import CORPUS_VERSION, MANIFEST_SCHEMA_VERSION

RESOLUTIONS = (128, 256)
CAMERAS = {"front": 0, "right": 90, "back": 180, "left": 270}
GENERATOR_VERSION = "analytic-aabb-orthographic/1"

# (label, xmin, xmax, ymin, ymax, zmin, zmax), in authored world units.
BOXES = (
    ("body", -.19, .19, -.14, .14, -.24, .17),
    ("head", -.15, .15, -.12, .12, .17, .38),
    ("left_arm", -.32, -.19, -.08, .08, -.13, .14),
    ("right_arm", .19, .29, -.08, .08, -.08, .14),
    ("left_leg", -.17, -.035, -.11, .11, -.43, -.24),
    ("right_leg", .035, .17, -.11, .11, -.43, -.24),
    ("small_flag", .15, .205, -.055, .055, .30, .35),
    ("backpack", -.10, .10, .14, .24, -.12, .10),
    ("nose", -.055, .055, -.24, -.12, .21, .28),
)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    split: str
    defect: str = "none"
    target: str = "front"
    parameter: float = 0.0
    information: str = "high_information"
    variant: int = 0


# Frozen before evaluation. Held-out cases are not used to choose policy values.
CASES = (
    CaseSpec("healthy", "calibration"),
    CaseSpec("bounded_shift", "calibration", "shift", parameter=.0625),
    CaseSpec("bounded_scale", "calibration", "scale", parameter=1.125),
    CaseSpec("crop", "calibration", "crop", parameter=.34),
    CaseSpec("empty_mask", "calibration", "empty_mask"),
    CaseSpec("empty_alpha", "calibration", "empty_alpha"),
    CaseSpec("alpha_mismatch", "calibration", "alpha_mismatch"),
    CaseSpec("unsupported_camera", "calibration", "perspective", information="ambiguous"),
    CaseSpec("ambiguous_camera", "calibration", "unverified_camera", information="ambiguous"),
    CaseSpec("duplicate_views", "calibration", "duplicate", target="right", information="ambiguous"),
    CaseSpec("missing_views", "calibration", "missing_views", information="insufficient"),
    CaseSpec("healthy_heldout", "heldout", variant=1),
    CaseSpec("shift_heldout", "heldout", "shift", target="back", parameter=-.046875, variant=1),
    CaseSpec("scale_heldout", "heldout", "scale", target="left", parameter=.90625, variant=1),
    CaseSpec("local_proportion", "heldout", "local_proportion", variant=1),
    CaseSpec("missing_small_part", "heldout", "missing_small_part"),
    CaseSpec("intentional_asymmetry", "heldout", "intentional_asymmetry", variant=2),
    CaseSpec("wrong_camera", "heldout", "wrong_camera", information="ambiguous", variant=1),
    CaseSpec("single_view", "heldout", "single_view", information="insufficient", variant=1),
    CaseSpec("empty_image_and_mask", "heldout", "empty_both", variant=1),
    CaseSpec("engine_failure_contract", "heldout", "engine_failure_contract", information="engine_failure"),
)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_boxes(variant: int = 0) -> tuple:
    boxes = list(BOXES)
    if variant:
        boxes[0] = ("body", -.18, .18, -.16, .16, -.22, .16)
        boxes[1] = ("head", -.13, .14, -.12, .13, .16, .36)
    if variant == 2:
        boxes[2] = ("left_arm", -.37, -.18, -.08, .08, -.18, .14)
        boxes.append(("intentional_left_fin", -.255, -.18, -.07, .07, .26, .39))
    return tuple(boxes)


def rectangles(boxes: tuple, angle: int) -> tuple:
    """Exact cardinal orthographic projection of AABBs; no sampled 3D model."""
    result = []
    for label, xmin, xmax, ymin, ymax, zmin, zmax in boxes:
        horizontal = {0: (xmin, xmax), 90: (ymin, ymax),
                      180: (-xmax, -xmin), 270: (-ymax, -ymin)}[angle]
        result.append((label, horizontal[0] + .5, horizontal[1] + .5, zmin + .5, zmax + .5))
    return tuple(result)


@lru_cache(maxsize=256)
def raster_mask(boxes: tuple, angle: int, size: int, *, shift=0.0, scale=1.0) -> bytes:
    projected = rectangles(boxes, angle)
    columns = tuple(((x / (size - 1) - .5 - shift) / scale + .5) for x in range(size))
    rows = tuple(((y / (size - 1) - .5) / scale + .5) for y in range(size))
    return bytes(int(any(x0 <= u <= x1 and y0 <= v <= y1
                         for _, x0, x1, y0, y1 in projected)) for v in rows for u in columns)


def rgba(mask: bytes, *, color=(66, 137, 192), empty_alpha=False) -> bytes:
    return bytes(channel for occupied in mask for channel in
                 ((*color, 255) if occupied and not empty_alpha else (0, 0, 0, 0)))


def png_bytes(size: int, pixels: bytes) -> bytes:
    """Minimal deterministic PNG RGBA writer, rows encoded in PNG top-left order."""
    if len(pixels) != size * size * 4:
        raise ValueError("RGBA size mismatch")
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    scanlines = b"".join(b"\0" + pixels[y*size*4:(y+1)*size*4] for y in reversed(range(size)))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scanlines, 9)) + chunk(b"IEND", b""))


def observations(spec: CaseSpec) -> dict:
    """Frozen expected D2 signals, plus deferred truth which D2 cannot establish."""
    required = {
        "shift": ["alignment.suspected"], "scale": ["alignment.suspected"],
        "crop": ["input.subject_truncated"], "empty_mask": ["input.empty_mask"],
        "empty_alpha": ["input.empty_alpha"], "empty_both": ["input.empty_mask", "input.empty_alpha"],
        "alpha_mismatch": ["input.alpha_mask_mismatch"], "perspective": ["camera.unsupported"],
        "unverified_camera": ["camera.unverified"], "wrong_camera": ["camera.unverified"],
        "duplicate": ["input.duplicate"], "missing_views": ["coverage.insufficient"],
        "single_view": ["coverage.insufficient"],
        "local_proportion": ["alignment.shape_mismatch"],
    }.get(spec.defect, [])
    if spec.defect in ("crop", "empty_mask", "empty_alpha", "empty_both", "alpha_mismatch", "perspective", "unverified_camera", "wrong_camera"):
        required += ["coverage.insufficient", "alignment.checked"]
    permitted = {
        "crop": ["alignment.shape_mismatch"],
        "empty_mask": ["input.alpha_mask_mismatch"],
        "empty_alpha": ["input.alpha_mask_mismatch"],
        "duplicate": ["alignment.shape_mismatch"],
        "perspective": ["alignment.reference_missing"],
        "unverified_camera": ["alignment.reference_missing"],
        "wrong_camera": ["alignment.reference_missing"],
        # A global silhouette registration check cannot guarantee a small part.
        "missing_small_part": ["alignment.shape_mismatch"],
    }.get(spec.defect, [])
    present = list(CAMERAS)
    if spec.defect == "missing_views":
        present.remove("left")
    if spec.defect == "single_view":
        present = ["front"]
    pass_requirements = []
    for name in present:
        for view_id in (name, f"ref_{name}"):
            pass_requirements.append({"code": "input.integrity", "view_id": view_id})
            if view_id != spec.target or spec.defect not in ("perspective", "unverified_camera", "wrong_camera"):
                pass_requirements.append({"code": "camera.support", "view_id": view_id})
        if name != spec.target or spec.defect in ("none", "intentional_asymmetry", "engine_failure_contract", "missing_views", "single_view"):
            pass_requirements.append({"code": "alignment.within_tolerance", "view_id": name})
    if len(present) == 4 and spec.defect not in ("crop", "empty_mask", "empty_alpha", "empty_both", "alpha_mismatch", "perspective", "unverified_camera", "wrong_camera"):
        pass_requirements.append({"code": "coverage.insufficient", "view_id": None})
    return {
        "required_codes": required,
        "required_statuses": {code: ("unknown" if code in ("camera.unverified", "input.duplicate", "alignment.checked", "alignment.shape_mismatch") else "fail") for code in required},
        "forbidden_codes": [] if spec.defect in ("shift", "scale") else ["alignment.suspected"],
        "permitted_codes": permitted,
        "pass_requirements": pass_requirements,
        "expected_abstention": spec.information != "high_information" or spec.defect in ("local_proportion", "missing_small_part"),
        "attribution": "No incorrect-view attribution is established by D2. D3 is unevaluated.",
        "target_view": spec.target if spec.defect not in ("none", "intentional_asymmetry", "engine_failure_contract") else None,
    }


def case_assets(spec: CaseSpec, size: int) -> tuple[dict, dict[str, bytes]]:
    boxes = source_boxes(spec.variant)
    view_names = list(CAMERAS)
    if spec.defect == "missing_views":
        view_names.remove("left")
    if spec.defect == "single_view":
        view_names = ["front"]
    files = {}
    views = []
    for name in view_names:
        angle = CAMERAS[name]
        true_angle = 90 if spec.defect == "wrong_camera" and name == spec.target else angle
        canonical_mask = raster_mask(boxes, angle, size)
        observed_boxes = boxes
        if name == spec.target and spec.defect == "local_proportion":
            observed_boxes = tuple((label, xmin, .42 if label == "right_arm" else xmax, ymin, ymax, zmin, zmax)
                                   for label, xmin, xmax, ymin, ymax, zmin, zmax in boxes)
        if name == spec.target and spec.defect == "missing_small_part":
            observed_boxes = tuple(box for box in boxes if box[0] != "small_flag")
        observed = raster_mask(observed_boxes, true_angle, size,
                               shift=spec.parameter if name == spec.target and spec.defect in ("shift", "crop") else 0,
                               scale=spec.parameter if name == spec.target and spec.defect == "scale" else 1)
        image_mask = observed
        if name == spec.target and spec.defect == "alpha_mismatch":
            image_mask = raster_mask(boxes, angle, size, shift=.10)
        if name == spec.target and spec.defect in ("empty_alpha", "empty_both"):
            image_mask = bytes(size*size)
        mask = bytes(size*size) if name == spec.target and spec.defect in ("empty_mask", "empty_both") else observed
        color = (66 + angle // 9, 137, 192 - angle // 9)
        # Exact same IMAGE bytes under two different declared cameras.
        if spec.defect == "duplicate" and name == spec.target:
            image_mask = raster_mask(boxes, 0, size)
            mask = image_mask
            color = (66, 137, 192)
        assets = {}
        for role, pixels in (("image", rgba(image_mask, color=color)), ("mask", rgba(mask, color=(255,255,255))),
                             ("reference", rgba(canonical_mask, color=color))):
            path = f"assets/{spec.case_id}/{size}/{name}-{role}.png"
            data = png_bytes(size, pixels)
            files[path] = data
            assets[role] = {"path": path, "sha256": sha256(data), "width": size, "height": size, "media_type": "image/png"}
        views.append({
            "view_id": name, "revision": "1", "assets": assets,
            "declared_camera": {"projection": "perspective" if name == spec.target and spec.defect == "perspective" else "orthographic",
                                "azimuth_degrees": angle, "elevation_degrees": 0, "flip_x": False,
                                "verified": not(name == spec.target and spec.defect in ("unverified_camera", "wrong_camera"))},
            "analytic_camera": {"projection": "orthographic", "azimuth_degrees": true_angle, "elevation_degrees": 0},
            "mask_occupied_pixels": sum(mask), "reference_occupied_pixels": sum(canonical_mask),
        })
    return {"resolution": size, "views": views}, files


def build_corpus(destination: Path) -> dict:
    """Write exact fixtures and hash manifest; safe to run repeatedly."""
    cases = []
    for spec in CASES:
        variants = []
        for size in RESOLUTIONS:
            variant, files = case_assets(spec, size)
            variants.append(variant)
            for path, data in files.items():
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        source = {"boxes": source_boxes(spec.variant), "projection": GENERATOR_VERSION,
                  "raster_coordinates": "bottom-left; u=x/(width-1), v=y/(height-1); inclusive rectangle edges"}
        source_path = f"sources/{spec.case_id}.json"
        (destination / source_path).parent.mkdir(parents=True, exist_ok=True)
        (destination / source_path).write_bytes(canonical_json(source))
        cases.append({
            "case_id": spec.case_id, "split": spec.split, "information_class": spec.information,
            "truth": {"kind": "analytic_synthetic", "real_world_ground_truth": False,
                      "source": source, "source_path": source_path, "source_sha256": sha256(canonical_json(source)),
                      "known_limits": ["Silhouettes do not observe concavities, texture, identity, topology or GLB fidelity.",
                                       "No human-reviewed generated or documentary images are included."]},
            "canonical_reference": {"validation": "exact analytic authorship", "human_validated": False,
                                    "intentional_asymmetry": True},
            "injection": {"kind": spec.defect, "view_id": spec.target, "parameter": spec.parameter,
                          "coordinate_unit": "normalized image fraction for shift; uniform factor for scale"},
            "expected": observations(spec), "variants": variants,
        })
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION, "corpus_version": CORPUS_VERSION,
        "generator": GENERATOR_VERSION, "license": "GPL-3.0-or-later, under the existing repository license; original mathematical regression data.",
        "provenance": {"kind": "original_analytic_authorship", "external_assets": [], "network_required": False,
                       "ai_generated": False, "renderer": "exact cardinal AABB projection; deterministic stdlib PNG encoder"},
        "partition_policy": "Case IDs and parameters frozen before evaluation; heldout is evaluation only, never threshold fitting.",
        "qualification_scope": {"D1": "shared contract serialization and UNKNOWN discipline", "D2": "real offline preflight",
                                "D3_D8": "unknown; downstream/human/provider/end-to-end acceptance not executed", "issue_84": "remains open"},
        "cases": cases,
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "manifest.json").write_bytes(canonical_json(manifest))
    return manifest
