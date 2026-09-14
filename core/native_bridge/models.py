from __future__ import annotations

from array import array
from dataclasses import dataclass

from ..image_mask import BinaryMask


@dataclass(frozen=True)
class NativeProjection:
    mask: BinaryMask
    azimuth_degrees: float
    elevation_degrees: float = 0.0
    flip_x: bool = False


@dataclass(frozen=True)
class NativeVolume:
    width: int
    depth: int
    height: int
    values: bytes
    occupied_count: int
    bounds: tuple[int, int, int, int, int, int] | None


@dataclass(frozen=True)
class NativeMesh:
    vertices: array
    indices: array
    polygon_starts: array
    polygon_sizes: array

    @property
    def vertex_count(self) -> int:
        return len(self.vertices) // 3

    @property
    def index_count(self) -> int:
        return len(self.indices)

    @property
    def polygon_count(self) -> int:
        return len(self.polygon_sizes)
