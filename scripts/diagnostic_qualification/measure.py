"""Measure archived pixels without inferring semantic identity or hidden geometry."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import zlib

from core.diagnostics_preflight import RasterInput, ViewInput
from core.diagnostics_preflight.registration import mask_from_input
from core.diagnostics_preflight.rasters import MAX_FILE_BYTES


def compare_images(healthy: Path, before: Path, after: Path, mask: Path) -> dict:
    """No resize, registration, colour fitting, or threshold selection after results."""
    rasters = {}
    assets = {}
    files = {}
    for name, path in (("healthy", healthy), ("before", before), ("after", after), ("mask", mask)):
        if path.stat().st_size > MAX_FILE_BYTES:
            return {"status": "unknown", "reason": "image_byte_budget:" + name, "assets": assets,
                    "semantic_identity_status": "unknown"}
        data = path.read_bytes()
        files[name] = data
        dimensions = None
        if (len(data) >= 33 and data[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" and
                zlib.crc32(data[12:29]) & 0xffffffff == struct.unpack(">I", data[29:33])[0]):
            dimensions = struct.unpack(">II", data[16:24])
        assets[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                        "width": dimensions[0] if dimensions else None,
                        "height": dimensions[1] if dimensions else None}
    grids = {(a["width"], a["height"]) for a in assets.values()}
    if all(a["width"] and a["height"] for a in assets.values()) and len(grids) != 1:
        return {"status": "fail", "reason": "image_grid_changed", "assets": assets,
                "dimension_source": "CRC-checked PNG IHDR; decoded pixel budget is not bypassed",
                "outside_pixels_status": "unknown", "semantic_identity_status": "unknown"}
    for name, data in files.items():
        raster = RasterInput.from_png_bytes(data)
        if raster.error:
            return {"status": "unknown", "reason": "unsupported_image:" + name,
                    "assets": assets, "semantic_identity_status": "unknown"}
        rasters[name] = raster
    shape = {(r.width, r.height) for r in rasters.values()}
    if len(shape) != 1:
        return {"status": "fail", "reason": "image_grid_changed", "assets": assets,
                "outside_pixels_status": "unknown", "semantic_identity_status": "unknown"}
    reference, original, candidate, region = (rasters[k].rgba for k in ("healthy", "before", "after", "mask"))
    support = mask_from_input(ViewInput(rasters["before"], mask=rasters["mask"]), .5, .5).values
    inside = [4 * i for i, editable in enumerate(support) if editable]
    if not inside:
        raise ValueError("An independently authored nonempty edit mask is required.")
    changed_outside = 0
    intersection = union = 0
    before_error = after_error = 0.
    overlay = bytearray()
    for i in range(0, len(reference), 4):
        editable = bool(support[i // 4])
        changed = original[i:i+4] != candidate[i:i+4]
        if changed and not editable:
            changed_outside += 1
        a, b = reference[i+3] >= .5, candidate[i+3] >= .5
        intersection += a and b
        union += a or b
        if editable:
            before_error += sum(abs(reference[i+j] - original[i+j]) for j in range(3))
            after_error += sum(abs(reference[i+j] - candidate[i+j]) for j in range(3))
        colour = (210, 45, 65, 255) if changed and not editable else (35, 145, 100, 255) if editable else (238, 241, 245, 255)
        overlay.extend(colour)
    before_error /= 3 * len(inside)
    after_error /= 3 * len(inside)
    return {"status": "measured", "assets": assets, "mask_pixels": len(inside),
            "masked_rgb_mean_absolute_error_before": before_error,
            "masked_rgb_mean_absolute_error_after": after_error,
            "numerical_improvement": before_error - after_error,
            "outside_mask_changed_pixels": changed_outside,
            "outside_pixels_status": "pass" if changed_outside == 0 else "fail",
            "outside_pixel_tolerance": 0, "alpha_threshold": .5,
            "mask_rgb_threshold": .5, "mask_convention": "D2 explicit mask: alpha >= .5 and max(RGB) >= .5",
            "foreground_alpha_iou": intersection / union if union else None,
            "semantic_identity_status": "unknown", "corrected_geometry_status": "unknown",
            "qualification_status": "unknown", "colour_space": "decoded display RGB; no photometric fitting",
            "overlay_rgba": bytes(overlay), "width": rasters["healthy"].width, "height": rasters["healthy"].height}


def write_comparison(healthy: Path, before: Path, after: Path, mask: Path, output: Path) -> dict:
    from scripts.appearance_diagnostic_corpus.authoring import png_rgba
    result = compare_images(healthy, before, after, mask)
    pixels = result.pop("overlay_rgba", None)
    if pixels is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        data = png_rgba(result["width"], result["height"], pixels)
        output.write_bytes(data)
        result["overlay"] = {"path": output.name, "sha256": hashlib.sha256(data).hexdigest(),
                             "legend": "red: changed outside mask; green: authored edit region; pale: remaining pixels"}
    return result
