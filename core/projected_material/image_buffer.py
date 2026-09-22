from __future__ import annotations
import math
from array import array
from dataclasses import dataclass
import bpy
from ..projection_math import clamp01

@dataclass(frozen=True)
class ImageBuffer:
    """
    Blender image copied into a Python float buffer.

    Reading bpy.types.Image.pixels repeatedly through RNA
    is expensive, so every projection image is copied once.
    """
    width: int
    height: int
    pixels: array

    @classmethod
    def from_blender_image(cls, image: bpy.types.Image) -> 'ImageBuffer':
        image.update()
        width = int(image.size[0])
        height = int(image.size[1])
        if width <= 0 or height <= 0:
            raise ValueError(f'Image "{image.name}" has invalid dimensions: {width}x{height}.')
        pixels = array('f', [0.0]) * (width * height * 4)
        image.pixels.foreach_get(pixels)
        return cls(width=width, height=height, pixels=pixels)

    def rgba(self, x: int, y: int) -> tuple[float, float, float, float]:
        x = max(0, min(self.width - 1, int(x)))
        y = max(0, min(self.height - 1, int(y)))
        index = (y * self.width + x) * 4
        return (float(self.pixels[index]), float(self.pixels[index + 1]), float(self.pixels[index + 2]), float(self.pixels[index + 3]))

    def sample_bilinear(self, u: float, v: float) -> tuple[float, float, float, float]:
        """
        Bilinear sampling in normalized image space.

        Blender image.pixels uses the same bottom-left
        convention as projection_math.py:

            u = 0 -> left
            u = 1 -> right

            v = 0 -> bottom
            v = 1 -> top
        """
        u = clamp01(u)
        v = clamp01(v)
        fx = u * float(self.width - 1)
        fy = v * float(self.height - 1)
        x0 = int(math.floor(fx))
        y0 = int(math.floor(fy))
        x1 = min(x0 + 1, self.width - 1)
        y1 = min(y0 + 1, self.height - 1)
        tx = fx - float(x0)
        ty = fy - float(y0)
        c00 = self.rgba(x0, y0)
        c10 = self.rgba(x1, y0)
        c01 = self.rgba(x0, y1)
        c11 = self.rgba(x1, y1)
        result: list[float] = []
        for channel in range(4):
            bottom = c00[channel] * (1.0 - tx) + c10[channel] * tx
            top = c01[channel] * (1.0 - tx) + c11[channel] * tx
            value = bottom * (1.0 - ty) + top * ty
            result.append(float(value))
        return (result[0], result[1], result[2], result[3])
