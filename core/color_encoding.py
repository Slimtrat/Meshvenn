"""Portable base-color byte textures are sRGB RGB with linear alpha."""
from __future__ import annotations
from array import array
import math


def linear_to_srgb(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Portable base color must be finite in [0, 1].")
    return value * 12.92 if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055


def encode_srgb_rgba(pixels):
    if len(pixels) % 4:
        raise ValueError("Base-color pixels must contain complete RGBA values.")
    encoded = array("f", pixels)
    for index in range(0, len(encoded), 4):
        for axis in range(3):
            encoded[index + axis] = linear_to_srgb(encoded[index + axis])
        # Alpha is coverage, never color-managed.
        if not math.isfinite(encoded[index + 3]) or not 0 <= encoded[index + 3] <= 1:
            raise ValueError("Portable alpha must be finite in [0, 1].")
    return encoded
