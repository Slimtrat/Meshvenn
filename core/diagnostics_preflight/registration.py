"""Conservative same-camera similarity proposals using ProjectionAlignment.

This is registration to an independently supported reference, not calibration
or a cross-view geometry diagnosis. No rotations, flips or shape warps exist.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from ..image_mask import BinaryMask
from ..projection_alignment import ProjectionAlignment
from .rasters import ViewInput


@dataclass(frozen=True)
class AlignmentAnchor:
    target_view_id: str
    reference_view_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if self.target_view_id == self.reference_view_id:
            raise ValueError("An alignment anchor must be an independent reference view.")
        if len(self.evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.evidence_sha256):
            raise ValueError("Anchor evidence must have a lowercase SHA-256 digest.")


@dataclass(frozen=True)
class AlignmentProposal:
    proposal_id: str
    view_id: str
    reference_view_id: str
    alignment: ProjectionAlignment
    before_iou: float
    after_iou: float
    dependency_fingerprint: str
    source_image_sha256: str
    source_mask_sha256: str | None
    reference_image_sha256: str
    reference_mask_sha256: str | None
    anchor_evidence_sha256: str
    transform_sha256: str


@dataclass(frozen=True)
class CertifiedProjectionInput:
    """One accepted mapping shared by geometry and appearance.

    Original immutable sources are preserved. Appearance samples original RGBA
    through source_uv; geometry uses aligned_mask. Both expose one certificate.
    """
    source: ViewInput
    aligned_mask: BinaryMask
    alignment: ProjectionAlignment
    certificate_sha256: str
    source_image_sha256: str
    source_mask_sha256: str | None

    @property
    def color_transform_sha256(self) -> str:
        return self.certificate_sha256

    @property
    def mask_transform_sha256(self) -> str:
        return self.certificate_sha256

    def color_at(self, target_u: float, target_v: float) -> tuple[float, float, float, float]:
        u, v = self.alignment.source_uv(target_u, target_v)
        image = self.source.image
        if not 0 <= u <= 1 or not 0 <= v <= 1:
            return 0.0, 0.0, 0.0, 0.0
        x = int(u * (image.width - 1) + 0.5)
        y = int(v * (image.height - 1) + 0.5)
        offset = (y * image.width + x) * 4
        return image.rgba[offset:offset + 4]


def mask_from_input(source: ViewInput, alpha_threshold: float, mask_threshold: float) -> BinaryMask:
    image = source.mask or source.image
    if source.mask:
        values = bytes(int(image.rgba[i + 3] >= alpha_threshold and
                           max(image.rgba[i:i + 3]) >= mask_threshold)
                       for i in range(0, len(image.rgba), 4))
    else:
        values = bytes(int(image.rgba[i] >= alpha_threshold)
                       for i in range(3, len(image.rgba), 4))
    return BinaryMask(image.width, image.height, values)


def mask_iou(first: BinaryMask, second: BinaryMask) -> float:
    if (first.width, first.height) != (second.width, second.height):
        raise ValueError("IoU requires a common raster grid.")
    intersection = sum(bool(a) and bool(b) for a, b in zip(first.values, second.values))
    union = sum(bool(a) or bool(b) for a, b in zip(first.values, second.values))
    return intersection / union if union else 0.0


def occupied_bounds(mask: BinaryMask) -> tuple[int, int, int, int] | None:
    left, bottom, right, top = mask.width, mask.height, -1, -1
    for index, value in enumerate(mask.values):
        if value:
            x, y = index % mask.width, index // mask.width
            left, bottom = min(left, x), min(bottom, y)
            right, top = max(right, x), max(top, y)
    return (left, bottom, right, top) if right >= 0 else None


def resample_mask(source: BinaryMask, width: int, height: int) -> BinaryMask:
    if (source.width, source.height) == (width, height):
        return source
    values = bytearray(width * height)
    for y in range(height):
        sy = int((y / (height - 1) if height > 1 else 0.5) * (source.height - 1) + 0.5)
        for x in range(width):
            sx = int((x / (width - 1) if width > 1 else 0.5) * (source.width - 1) + 0.5)
            values[y * width + x] = source.values[sy * source.width + sx]
    return BinaryMask(width, height, bytes(values))


def fit_similarity(source: BinaryMask, reference: BinaryMask, *, min_scale: float,
                   max_scale: float, max_offset: float) -> tuple[ProjectionAlignment, float, float] | None:
    """Search at at most 128x128; certify the winner against the native masks.

    Downsampling bounds search work only. Returned before/after measurements
    always come from complete original masks at the source native resolution.
    """
    native_reference = resample_mask(reference, source.width, source.height)
    factor = min(1., 128 / max(source.width, source.height))
    width, height = max(2, round(source.width * factor)), max(2, round(source.height * factor))
    if source.width < 2 or source.height < 2:
        return None
    fit = _fit_grid(resample_mask(source, width, height), resample_mask(reference, width, height),
                    min_scale=min_scale, max_scale=max_scale, max_offset=max_offset)
    if fit is None:
        return None
    alignment = fit[0]
    if not _keeps_bounds(occupied_bounds(source), source, alignment):
        return None
    return alignment, mask_iou(source, native_reference), mask_iou(alignment.align_mask(source), native_reference)


def _fit_grid(source: BinaryMask, reference: BinaryMask, *, min_scale: float,
              max_scale: float, max_offset: float) -> tuple[ProjectionAlignment, float, float] | None:
    """Fit a bounded uniform scale/translation; residuals decide suitability.

    A bbox suggests candidates, never proves a match. We reject unequal axis
    scaling and evaluate actual occupied pixels after ProjectionAlignment's
    authoritative nearest-neighbor mapping. The search has a fixed 125 budget.
    """
    reference = resample_mask(reference, source.width, source.height)
    bounds, target = occupied_bounds(source), occupied_bounds(reference)
    if bounds is None or target is None or source.width < 2 or source.height < 2:
        return None
    x0, y0, x1, y1 = bounds
    tx0, ty0, tx1, ty1 = target
    # Inclusive pixel support is more stable for filled rasters than endpoint
    # lengths. The small search below accounts for nearest-neighbor rounding.
    sx, sy = (tx1 - tx0 + 1) / (x1 - x0 + 1), (ty1 - ty0 + 1) / (y1 - y0 + 1)
    if abs(math.log(sx / sy)) > 0.04:
        return None
    scale = (sx + sy) / 2
    source_u = (x0 + x1) / (2 * (source.width - 1))
    source_v = (y0 + y1) / (2 * (source.height - 1))
    target_u = (tx0 + tx1) / (2 * (source.width - 1))
    target_v = (ty0 + ty1) / (2 * (source.height - 1))
    if not min_scale <= scale <= max_scale:
        return None
    step = 1 / max(tx1 - tx0 + 1, ty1 - ty0 + 1)
    best, before, score = ProjectionAlignment(), mask_iou(source, reference), -1.0
    for ds in (-1, -0.5, 0, 0.5, 1):
        candidate_scale = scale + ds * step
        if not min_scale <= candidate_scale <= max_scale:
            continue
        offset_u = target_u - 0.5 - candidate_scale * (source_u - 0.5)
        offset_v = target_v - 0.5 - candidate_scale * (source_v - 0.5)
        for dx in (-1, -0.5, 0, 0.5, 1):
            for dy in (-1, -0.5, 0, 0.5, 1):
                u = offset_u + dx / (source.width - 1)
                v = offset_v + dy / (source.height - 1)
                if abs(u) > max_offset or abs(v) > max_offset:
                    continue
                candidate = ProjectionAlignment(u, v, candidate_scale)
                # Never improve overlap by losing an occupied part off-canvas.
                if not _keeps_bounds(bounds, source, candidate):
                    continue
                value = mask_iou(candidate.align_mask(source), reference)
                if value > score:
                    best, score = candidate, value
    return (best, before, score) if score >= 0 else None


def _keeps_bounds(bounds, source, alignment) -> bool:
    x0, y0, x1, y1 = bounds
    for x, y in ((x0, y0), (x1, y1)):
        u = 0.5 + alignment.scale * (x / (source.width - 1) - 0.5) + alignment.offset_u
        v = 0.5 + alignment.scale * (y / (source.height - 1) - 0.5) + alignment.offset_v
        if not 0 < u < 1 or not 0 < v < 1:
            return False
    return True


def transform_hash(alignment: ProjectionAlignment, *dependencies: str | None) -> str:
    payload = {"alignment": alignment.as_dict(), "dependencies": dependencies,
               "sampling": "ProjectionAlignment.pixel-centers.nearest.v1"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
