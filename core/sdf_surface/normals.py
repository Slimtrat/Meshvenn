from __future__ import annotations

import math

from ..sdf import SDFVolume
from .models import DEFAULT_GRADIENT_STEP_SCALE, Vector3
from .numeric import normalize3


def estimate_sdf_normal(
    volume: SDFVolume,
    position: Vector3,
    *,
    step_scale: float = DEFAULT_GRADIENT_STEP_SCALE,
) -> Vector3:
    """Estimate the outward SDF gradient at a normalized position."""

    step_scale = float(step_scale)
    if not math.isfinite(step_scale) or step_scale <= 0.0:
        raise ValueError("step_scale must be finite and positive.")

    hx = (2.0 / float(volume.width - 1)) * step_scale
    hy = (2.0 / float(volume.depth - 1)) * step_scale
    hz = (2.0 / float(volume.height - 1)) * step_scale
    x, y, z = position
    dx = (
        volume.sample_normalized(x + hx, y, z)
        - volume.sample_normalized(x - hx, y, z)
    ) / (2.0 * hx)
    dy = (
        volume.sample_normalized(x, y + hy, z)
        - volume.sample_normalized(x, y - hy, z)
    ) / (2.0 * hy)
    dz = (
        volume.sample_normalized(x, y, z + hz)
        - volume.sample_normalized(x, y, z - hz)
    ) / (2.0 * hz)
    return normalize3((dx, dy, dz))
