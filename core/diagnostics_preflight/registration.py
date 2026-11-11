"""Conservative same-camera similarity proposals using ProjectionAlignment.

This is registration to an independently supported reference, not calibration
or a cross-view geometry diagnosis. No rotations, flips or shape warps exist.
"""
from __future__ import annotations

import hashlib
import json
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


def _scale_interval(bounds, target, minimum, maximum):
    """Intersect uniform-scale intervals allowed by pixel support rounding.

    A discrete bbox extent is uncertain by one endpoint pixel before and after
    nearest-neighbor sampling. Point width/height ratios can disagree even for
    a genuine uniform transform; disjoint intervals still reject axis warping.
    """
    x0, y0, x1, y1 = bounds
    tx0, ty0, tx1, ty1 = target
    extents = ((x1-x0+1, tx1-tx0+1), (y1-y0+1, ty1-ty0+1))
    low, high = minimum, maximum
    for original, expected in extents:
        low = max(low, max(1, expected-1)/(original+1))
        high = min(high, (expected+1)/max(1, original-1))
    return (low, high) if low <= high else None


def fit_similarity(source: BinaryMask, reference: BinaryMask, *, min_scale: float,
                   max_scale: float, max_offset: float) -> tuple[ProjectionAlignment, float, float] | None:
    """Search at at most 128x128; certify finalists against native masks.

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
    bounds, target_bounds = occupied_bounds(source), occupied_bounds(native_reference)
    candidates = [fit[0]] if fit else []
    # A native bbox finalist avoids quantization of the reduced search choosing
    # a transform that is measurably worse on the complete image.
    if bounds and target_bounds:
        x0, y0, x1, y1 = bounds
        tx0, ty0, tx1, ty1 = target_bounds
        interval = _scale_interval(bounds, target_bounds, min_scale, max_scale)
        if interval:
            scale = sum(interval)/2
            u = (tx0+tx1)/(2*(source.width-1))-.5-scale*((x0+x1)/(2*(source.width-1))-.5)
            v = (ty0+ty1)/(2*(source.height-1))-.5-scale*((y0+y1)/(2*(source.height-1))-.5)
            if abs(u) <= max_offset and abs(v) <= max_offset:
                candidates.append(ProjectionAlignment(u, v, scale))
    before = mask_iou(source, native_reference)
    finalists = []
    for alignment in candidates:
        if not _keeps_bounds(bounds, source, alignment):
            continue
        aligned = alignment.align_mask(source)
        finalists.append((mask_iou(aligned, native_reference), alignment, aligned))
    for score, alignment, aligned in sorted(finalists, key=lambda item: item[0], reverse=True):
        if _retains_components(source, native_reference, alignment, aligned):
            return alignment, before, score
    return None


def _component_signature(mask: BinaryMask, sampled: bytearray | None = None) -> tuple[int, int]:
    """Count eight-connected foreground components and wholly lost components."""
    visited = bytearray(len(mask.values))
    count = lost = 0
    width, height = mask.width, mask.height
    for seed, value in enumerate(mask.values):
        if not value or visited[seed]:
            continue
        count += 1
        visited[seed] = 1
        pending, retained = [seed], sampled is None
        while pending:
            index = pending.pop()
            if sampled is not None and sampled[index]:
                retained = True
            x, y = index % width, index // width
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if mask.values[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        pending.append(neighbor)
        lost += int(not retained)
    return count, lost


def _retains_components(source: BinaryMask, reference: BinaryMask,
                        alignment: ProjectionAlignment, aligned: BinaryMask) -> bool:
    """Never reward nearest-neighbor aliasing that erases an occupied component.

    Global IoU can hide loss of an entire thin isolated part. Bind every original
    component to actually selected source pixels, and conservatively abstain if
    component topology differs from the independent reference or changes during
    registration. This does not certify semantic details inside one component.
    """
    sampled = bytearray(len(source.values))
    xs = [alignment.source_uv(x / (source.width - 1), .5)[0] for x in range(source.width)]
    ys = [alignment.source_uv(.5, y / (source.height - 1))[1] for y in range(source.height)]
    for v in ys:
        if not 0 <= v <= 1:
            continue
        sy = int(v * (source.height - 1) + .5)
        for u in xs:
            if 0 <= u <= 1:
                sx = int(u * (source.width - 1) + .5)
                sampled[sy * source.width + sx] = 1
    source_count, lost = _component_signature(source, sampled)
    return (not lost and source_count == _component_signature(reference)[0] ==
            _component_signature(aligned)[0])


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
    interval = _scale_interval(bounds, target, min_scale, max_scale)
    if interval is None:
        return None
    source_u = (x0 + x1) / (2 * (source.width - 1))
    source_v = (y0 + y1) / (2 * (source.height - 1))
    target_u = (tx0 + tx1) / (2 * (source.width - 1))
    target_v = (ty0 + ty1) / (2 * (source.height - 1))
    best, before, score = ProjectionAlignment(), mask_iou(source, reference), -1.0
    low, high = interval
    for index in range(5):
        candidate_scale = low + (high-low)*index/4
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
