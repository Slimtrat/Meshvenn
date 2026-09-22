"""Per-view silhouette registration shared by geometry and material input.

Offsets are fractions of image width/height in bottom-left-origin coordinates.
Scale is uniform around the image center: values above one enlarge the source
subject. Registration is applied in image coordinates before optional Flip X.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .image_mask import BinaryMask


@dataclass(frozen=True)
class ProjectionAlignment:
    offset_u: float = 0.0
    offset_v: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.offset_u, self.offset_v, self.scale)):
            raise ValueError("Projection alignment parameters must be finite.")
        if not -0.5 <= self.offset_u <= 0.5 or not -0.5 <= self.offset_v <= 0.5:
            raise ValueError("Projection alignment offsets must be inside [-0.5, 0.5].")
        if not 0.25 <= self.scale <= 4.0:
            raise ValueError("Projection alignment scale must be inside [0.25, 4].")

    @property
    def is_identity(self) -> bool:
        return self.offset_u == 0.0 and self.offset_v == 0.0 and self.scale == 1.0

    def source_uv(self, target_u: float, target_v: float) -> tuple[float, float]:
        """Map an aligned pixel to the original image without edge clamping."""

        if not math.isfinite(target_u) or not math.isfinite(target_v):
            raise ValueError("Projection coordinates must be finite.")
        return (
            (target_u - 0.5 - self.offset_u) / self.scale + 0.5,
            (target_v - 0.5 - self.offset_v) / self.scale + 0.5,
        )

    def align_mask(self, source: BinaryMask) -> BinaryMask:
        """Resample a source mask on its native grid with outside pixels empty.

        Nearest-neighbour sampling uses the same pixel-center convention as the
        C++ visual hull, so no interpolation can invent occupied silhouettes.
        """

        if self.is_identity:
            return source
        width, height = source.width, source.height

        def mapped_axis(size: int, offset: float) -> tuple[int, ...]:
            positions = []
            for index in range(size):
                target = index / (size - 1) if size > 1 else 0.5
                original = (target - 0.5 - offset) / self.scale + 0.5
                positions.append(
                    int(original * (size - 1) + 0.5)
                    if 0.0 <= original <= 1.0 else -1
                )
            return tuple(positions)

        source_x_by_target = mapped_axis(width, self.offset_u)
        source_y_by_target = mapped_axis(height, self.offset_v)
        aligned = bytearray(width * height)
        for y, source_y in enumerate(source_y_by_target):
            if source_y < 0:
                continue
            destination_row = y * width
            source_row = source_y * width
            for x, source_x in enumerate(source_x_by_target):
                if source_x >= 0:
                    aligned[destination_row + x] = source.values[source_row + source_x]
        return BinaryMask(width, height, bytes(aligned))

    def as_dict(self) -> dict[str, float]:
        return {
            "offset_u": self.offset_u,
            "offset_v": self.offset_v,
            "scale": self.scale,
        }
