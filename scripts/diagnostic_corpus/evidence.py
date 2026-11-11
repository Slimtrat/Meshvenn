"""Actual pixel evidence from decoded inputs, not decorative sample diagrams."""

from __future__ import annotations

from .fixtures import png_bytes


def difference_overlay(observed: bytes, reference: bytes, size: int) -> bytes:
    if len(observed) != size*size or len(reference) != size*size:
        raise ValueError("Overlay masks must match the declared resolution")
    colors = {(0, 0): (250, 250, 250, 255), (1, 1): (70, 80, 90, 255),
              (0, 1): (225, 55, 60, 255), (1, 0): (20, 130, 235, 255)}
    pixels = bytes(channel for a, b in zip(observed, reference) for channel in colors[(int(bool(a)), int(bool(b)))])
    return png_bytes(size, pixels)


def binary_alpha(raster) -> bytes:
    return bytes(int(raster.rgba[i] >= .1) for i in range(3, len(raster.rgba), 4))
