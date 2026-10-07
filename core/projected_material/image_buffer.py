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
    # Association/encoding describe the copied RNA buffer, not the file's
    # alpha_mode label: FILE PNG16 RNA is linear PREMUL even when tagged STRAIGHT.
    # Direct buffers default to straight scene-linear RGBA.
    alpha_mode: str = 'STRAIGHT'
    rgb_encoding: str = 'scene-linear'
    source_alpha_mode: str | None = None

    @classmethod
    def from_blender_image(cls, image: bpy.types.Image) -> 'ImageBuffer':
        image.update()
        width = int(image.size[0])
        height = int(image.size[1])
        if width <= 0 or height <= 0:
            raise ValueError(f'Image "{image.name}" has invalid dimensions: {width}x{height}.')
        pixels = array('f', [0.0]) * (width * height * 4)
        image.pixels.foreach_get(pixels)
        return cls.from_copied_blender_pixels(image, pixels, width=width, height=height)

    @classmethod
    def from_copied_blender_pixels(cls, image: bpy.types.Image, pixels: array, *,
                                  width: int, height: int) -> 'ImageBuffer':
        """Annotate an existing raw copy shared with silhouette processing."""
        declared = getattr(image, 'alpha_mode', 'STRAIGHT')
        floating = getattr(image, 'is_float', True)
        generated = getattr(image, 'source', 'GENERATED') == 'GENERATED'
        colorspace = getattr(getattr(image, 'colorspace_settings', None), 'name',
                             'Linear Rec.709' if floating else 'sRGB')
        supported = colorspace in ('sRGB', 'Linear Rec.709', 'Non-Color')
        encoding = ('scene-linear' if floating or colorspace != 'sRGB' else 'sRGB')
        if not supported:
            encoding = f'unsupported:{colorspace}'
        if not floating and declared == 'PREMUL':
            # Associated byte ingress is not qualified as source color: its
            # quantization is magnified by unassociation, and Blender's shader
            # interpretation differs from our explicit buffer math contract.
            # Keep raw INPUT reads legal, but refuse at the MATERIAL boundary.
            encoding = 'unsupported:premultiplied-byte-ingress'
        association = declared
        if not generated and declared in ('STRAIGHT', 'PREMUL') and colorspace != 'Non-Color':
            # Blender's loaded float pixels are associated scene-linear; loaded
            # byte pixels are straight encoded UNORM. Neither matches the file
            # label reliably. Keep raw reads intact and normalize only sampling.
            association = 'PREMUL' if floating else 'STRAIGHT'
        return cls(width=width, height=height, pixels=pixels, alpha_mode=association,
                   rgb_encoding=encoding, source_alpha_mode=declared)

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

    def sample_bilinear_alpha_aware(self, u: float, v: float) -> tuple[float, float, float, float]:
        """Filter color without letting transparent background darken edges.

        Alpha remains the filtered coverage/confidence. RGB is filtered in
        premultiplied space and returned straight for the opaque projected
        material. The historical channel-wise ``sample_bilinear`` is unchanged.
        CHANNEL_PACKED alpha is not coverage and must not be guessed as such.
        NONE explicitly ignores alpha, matching an opaque source image.
        """
        self.validate_coverage_alpha_mode()
        u, v = clamp01(u), clamp01(v)
        fx, fy = u * (self.width - 1), v * (self.height - 1)
        x0, y0 = int(math.floor(fx)), int(math.floor(fy))
        x1, y1 = min(x0 + 1, self.width - 1), min(y0 + 1, self.height - 1)
        tx, ty = fx - x0, fy - y0
        samples = ((self.rgba(x0, y0), (1 - tx) * (1 - ty)),
                   (self.rgba(x1, y0), tx * (1 - ty)),
                   (self.rgba(x0, y1), (1 - tx) * ty),
                   (self.rgba(x1, y1), tx * ty))
        alpha = red = green = blue = 0.0
        for color, weight in samples:
            if weight == 0:
                continue
            coverage = 1.0 if self.alpha_mode == 'NONE' else color[3]
            if not math.isfinite(coverage) or not 0 <= coverage <= 1:
                raise ValueError('Projected coverage alpha must be finite in [0, 1].')
            # Ignore RGB completely at zero coverage, including a nonzero RGB
            # matte or undefined PREMUL color on fully transparent pixels.
            if coverage == 0:
                continue
            if not all(math.isfinite(channel) for channel in color[:3]):
                raise ValueError('Projected covered RGB must be finite.')
            rgb = color[:3]
            if self.rgb_encoding == 'sRGB':
                # A byte PREMUL buffer is associated in its encoded space.
                # Unassociate before the nonlinear conversion, then filter in
                # associated scene-linear space like every other source.
                if self.alpha_mode == 'PREMUL':
                    rgb = tuple(channel / coverage for channel in rgb)
                rgb = tuple(channel / 12.92 if channel <= .04045 else
                            ((channel + .055) / 1.055) ** 2.4 for channel in rgb)
                color_weight = weight * coverage
            else:
                color_weight = weight if self.alpha_mode == 'PREMUL' else weight * coverage
            red += rgb[0] * color_weight
            green += rgb[1] * color_weight
            blue += rgb[2] * color_weight
            alpha += coverage * weight
        if alpha <= 0:
            return (0.0, 0.0, 0.0, 0.0)
        return (red / alpha, green / alpha, blue / alpha, alpha)

    def validate_coverage_alpha_mode(self) -> None:
        """Cheap MATERIAL-boundary check; no mutation or whole-image scan.

        Geometry and historical channel-wise sampling can still carry packed
        channels. Only the color projection stage interprets alpha as coverage.
        """
        if self.alpha_mode not in ('STRAIGHT', 'PREMUL', 'NONE'):
            raise ValueError(f'Projected color requires coverage alpha, not {self.alpha_mode!r}.')
        if self.rgb_encoding not in ('scene-linear', 'sRGB'):
            raise ValueError(f'Projected color encoding is not certified: {self.rgb_encoding!r}.')

    def validate_coverage_data(self) -> None:
        """Validate source data once before a MATERIAL stage can mutate UVs.

        Legacy sources may contain finite HDR RGB. Fully transparent RGB is
        undefined and ignored; NONE alpha is not coverage and is ignored too.
        The typed appearance contract separately enforces its stricter [0, 1].
        """
        self.validate_coverage_alpha_mode()
        if (type(self.width) is not int or type(self.height) is not int or
                self.width <= 0 or self.height <= 0 or
                len(self.pixels) != self.width * self.height * 4):
            raise ValueError('Projected color requires valid RGBA buffer dimensions.')
        for index in range(0, len(self.pixels), 4):
            alpha = 1.0 if self.alpha_mode == 'NONE' else self.pixels[index + 3]
            if not math.isfinite(alpha) or not 0 <= alpha <= 1:
                raise ValueError('Projected coverage alpha must be finite in [0, 1].')
            if alpha > 0 and not all(math.isfinite(self.pixels[index + axis]) for axis in range(3)):
                raise ValueError('Projected covered RGB must be finite.')
