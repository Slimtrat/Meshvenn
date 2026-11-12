"""Alpha-aware scene-linear sampling of immutable original decoded buffers."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..diagnostics_preflight import ViewInput
from ..diagnostics_preflight.registration import mask_from_input
from .policy import AppearanceViewSettings


@dataclass(frozen=True)
class ColorSample:
    raw_rgb: tuple[float, float, float] | None
    rgb: tuple[float, float, float] | None
    alpha: float
    state: str
    reason: str


def srgb_to_linear(value):
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def sample_color(data: ViewInput, uv, settings: AppearanceViewSettings, *, min_alpha=.95,
                 boundary_tolerance=.06, subject_mask=None):
    """Filter covered RGB in scene-linear space; unknown encodings stay unknown.

    Contrasting source texels identify an unresolved finite-raster boundary.
    They do not become an interpolated invented paint color or an identity fault.
    """
    u, v = uv
    if not all(math.isfinite(value) for value in uv) or not (0 <= u <= 1 and 0 <= v <= 1):
        return ColorSample(None, None, 0., "outside", "Sample is outside the original source image.")
    raster = data.image
    width, height = raster.width, raster.height
    if not width or not height or len(raster.rgba) != width*height*4:
        return ColorSample(None, None, 0., "invalid", "Source buffer is unavailable.")
    if subject_mask is None:
        subject_mask = mask_from_input(data, .1, .5)
    if subject_mask is not None:
        mx, my = int(u*(subject_mask.width-1)+.5), int(v*(subject_mask.height-1)+.5)
        if not subject_mask.values[my*subject_mask.width+mx]:
            return ColorSample(None, None, 0., "transparent", "The declared subject mask does not cover the sample.")
    px, py = u*(width-1), v*(height-1)
    x, y = int(px), int(py)
    fx, fy = px-x, py-y
    corners = ((x, y, (1-fx)*(1-fy)), (min(x+1,width-1), y, fx*(1-fy)),
               (x, min(y+1,height-1), (1-fx)*fy),
               (min(x+1,width-1), min(y+1,height-1), fx*fy))
    total_alpha, rgb, samples = 0., [0., 0., 0.], []
    for sx, sy, weight in corners:
        if weight <= 1e-12:
            continue
        pixel = raster.rgba[(sy*width+sx)*4:(sy*width+sx)*4+4]
        if subject_mask is not None:
            mask_x = int((sx/(width-1) if width > 1 else .5)*(subject_mask.width-1)+.5)
            mask_y = int((sy/(height-1) if height > 1 else .5)*(subject_mask.height-1)+.5)
            if not subject_mask.values[mask_y*subject_mask.width+mask_x]:
                return ColorSample(None, None, 0., "boundary", "A source subject-mask boundary is underresolved.")
        alpha = pixel[3]
        if not 0 <= alpha <= 1:
            return ColorSample(None, None, 0., "invalid", "Covered alpha is invalid.")
        if alpha < min_alpha:
            return ColorSample(None, None, alpha, "boundary", "A source alpha boundary is underresolved.")
        if settings.color_space == "unknown":
            return ColorSample(None, None, alpha, "unknown_encoding", "Source color encoding is undeclared.")
        color = tuple(srgb_to_linear(c) if settings.color_space == "sRGB" else c for c in pixel[:3])
        if any(not math.isfinite(c) or not 0 <= c <= 1 for c in color):
            return ColorSample(None, None, alpha, "invalid", "Covered source RGB is not finite and normalized.")
        samples.append(color)
        for axis in range(3):
            rgb[axis] += weight*alpha*color[axis]
        total_alpha += weight*alpha
    if total_alpha < min_alpha:
        return ColorSample(None, None, total_alpha, "transparent", "The source has insufficient opaque support.")
    raw = tuple(c/total_alpha for c in rgb)
    # Match the nearest-sample native convention without silently inventing a
    # color at a texture boundary in a different source raster.
    if any(max(abs(a-b) for a,b in zip(a_color,b_color)) > boundary_tolerance
           for a_color in samples for b_color in samples):
        return ColorSample(raw, None, total_alpha, "boundary", "Source texel contrast exceeds the supported color footprint.")
    if not settings.calibrated:
        return ColorSample(raw, raw, total_alpha, "uncontrolled", "Illumination or color calibration is unverified.")
    normalized = tuple(c/settings.linear_gain for c in raw)
    if (any(c > 1+1e-6 for c in normalized) or
            settings.photometry == "calibrated" and settings.linear_gain > 1 and any(c >= 1-1e-8 for c in raw)):
        return ColorSample(raw, None, total_alpha, "clipped", "Declared exposure cannot recover saturated source information.")
    return ColorSample(raw, tuple(min(1., c) for c in normalized), total_alpha, "comparable",
                       "Opaque scene-linear sample under declared producer photometry.")


def foreground(data: ViewInput, uv, *, subject_mask=None):
    if subject_mask is None:
        subject_mask = mask_from_input(data, .1, .5)
    u,v = uv
    if not (0 <= u <= 1 and 0 <= v <= 1):
        return False
    x,y = int(u*(subject_mask.width-1)+.5), int(v*(subject_mask.height-1)+.5)
    return bool(subject_mask.values[y*subject_mask.width+x])
