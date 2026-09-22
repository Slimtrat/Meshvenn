from __future__ import annotations

import math
from array import array
from dataclasses import dataclass

from .constants import DEFAULT_ISO_LEVEL
from .utils import clamp, lerp, require_finite


@dataclass(frozen=True)
class SDFVolume:
    """Dense scalar field sampled on a regular normalized grid, with x fastest."""

    width: int
    depth: int
    height: int
    values: array
    iso_level: float = DEFAULT_ISO_LEVEL

    def __post_init__(self) -> None:
        for name, value in (
            ("width", self.width),
            ("depth", self.depth),
            ("height", self.height),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 2:
                raise ValueError(f"{name} must be an integer >= 2.")
        expected = self.width * self.depth * self.height
        copied = array("f", self.values)
        if len(copied) != expected:
            raise ValueError(f"SDF volume contains {len(copied)} values, expected {expected}.")
        if any(not math.isfinite(float(value)) for value in copied):
            raise ValueError("SDF volume contains a non-finite sample.")
        object.__setattr__(self, "values", copied)
        object.__setattr__(self, "iso_level", require_finite(self.iso_level, name="iso_level"))

    @property
    def sample_count(self) -> int:
        return self.width * self.depth * self.height

    @property
    def dimensions(self) -> tuple[int, int, int]:
        return self.width, self.depth, self.height

    def index(self, x: int, y: int, z: int) -> int:
        if (
            x < 0 or x >= self.width
            or y < 0 or y >= self.depth
            or z < 0 or z >= self.height
        ):
            raise IndexError("SDF volume coordinate outside bounds.")
        return (z * self.depth + y) * self.width + x

    def get(self, x: int, y: int, z: int) -> float:
        return float(self.values[self.index(x, y, z)])

    def inside(self, x: int, y: int, z: int, *, iso_level: float | None = None) -> bool:
        resolved_iso = self.iso_level if iso_level is None else require_finite(iso_level, name="iso_level")
        return self.get(x, y, z) <= resolved_iso

    @property
    def minimum_value(self) -> float:
        return float(min(self.values))

    @property
    def maximum_value(self) -> float:
        return float(max(self.values))

    @property
    def has_inside_samples(self) -> bool:
        return any(float(value) <= self.iso_level for value in self.values)

    @property
    def has_outside_samples(self) -> bool:
        return any(float(value) > self.iso_level for value in self.values)

    @property
    def crosses_surface(self) -> bool:
        return self.has_inside_samples and self.has_outside_samples

    def to_occupancy_bytes(self, *, iso_level: float | None = None) -> bytes:
        resolved_iso = self.iso_level if iso_level is None else require_finite(iso_level, name="iso_level")
        result = bytearray(self.sample_count)
        for index, value in enumerate(self.values):
            result[index] = 1 if float(value) <= resolved_iso else 0
        return bytes(result)

    def sample_normalized(self, x: float, y: float, z: float) -> float:
        """Trilinear sample in normalized reconstruction space."""
        x = clamp(require_finite(x, name="x"), -1.0, 1.0)
        y = clamp(require_finite(y, name="y"), -1.0, 1.0)
        z = clamp(require_finite(z, name="z"), -1.0, 1.0)
        gx = (x + 1.0) * 0.5 * float(self.width - 1)
        gy = (y + 1.0) * 0.5 * float(self.depth - 1)
        gz = (z + 1.0) * 0.5 * float(self.height - 1)
        x0, y0, z0 = int(math.floor(gx)), int(math.floor(gy)), int(math.floor(gz))
        x1 = min(x0 + 1, self.width - 1)
        y1 = min(y0 + 1, self.depth - 1)
        z1 = min(z0 + 1, self.height - 1)
        tx, ty, tz = gx - float(x0), gy - float(y0), gz - float(z0)
        x00 = lerp(self.get(x0, y0, z0), self.get(x1, y0, z0), tx)
        x10 = lerp(self.get(x0, y1, z0), self.get(x1, y1, z0), tx)
        x01 = lerp(self.get(x0, y0, z1), self.get(x1, y0, z1), tx)
        x11 = lerp(self.get(x0, y1, z1), self.get(x1, y1, z1), tx)
        return lerp(lerp(x00, x10, ty), lerp(x01, x11, ty), tz)

    def cell_crosses_surface(
        self, x: int, y: int, z: int, *, iso_level: float | None = None
    ) -> bool:
        if (
            x < 0 or x >= self.width - 1
            or y < 0 or y >= self.depth - 1
            or z < 0 or z >= self.height - 1
        ):
            raise IndexError("SDF cell coordinate outside bounds.")
        iso = self.iso_level if iso_level is None else require_finite(iso_level, name="iso_level")
        values = (
            self.get(x, y, z), self.get(x + 1, y, z),
            self.get(x, y + 1, z), self.get(x + 1, y + 1, z),
            self.get(x, y, z + 1), self.get(x + 1, y, z + 1),
            self.get(x, y + 1, z + 1), self.get(x + 1, y + 1, z + 1),
        )
        minimum, maximum = min(values), max(values)
        return minimum <= iso <= maximum and minimum < maximum
