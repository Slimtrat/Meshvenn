"""Explicit glTF coordinate and upstream height-normalization provenance."""

from __future__ import annotations

from dataclasses import dataclass

from .validation import fields, number


@dataclass(frozen=True)
class NormalizationConvention:
    normalized_height: bool
    target_height: float | None
    scale: float
    convention: str = "meshvenn-height-v1"

    def __post_init__(self):
        if self.convention != "meshvenn-height-v1":
            raise ValueError("Unsupported normalization convention.")
        if not isinstance(self.normalized_height, bool):
            raise TypeError("normalized_height must be a boolean.")
        object.__setattr__(self, "scale", number(self.scale, name="normalization scale", positive=True))
        if self.normalized_height:
            object.__setattr__(self, "target_height", number(
                self.target_height, name="target_height", positive=True))
        elif self.target_height is not None or self.scale != 1.0:
            raise ValueError("Disabled height normalization requires null target_height and scale 1.")

    @classmethod
    def from_dict(cls, value):
        fields(value, ("convention", "normalized_height", "target_height", "scale"),
               name="normalization")
        return cls(**value)

    def to_dict(self):
        return {"convention": self.convention, "normalized_height": self.normalized_height,
                "target_height": self.target_height, "scale": self.scale}


@dataclass(frozen=True)
class CoordinateConvention:
    normalization: NormalizationConvention
    units: str = "meters"
    up_axis: str = "Y"
    forward_axis: str = "+Z"
    handedness: str = "right"

    def __post_init__(self):
        if not isinstance(self.normalization, NormalizationConvention):
            raise TypeError("coordinates require a NormalizationConvention.")
        if (self.units, self.up_axis, self.forward_axis, self.handedness) != (
                "meters", "Y", "+Z", "right"):
            raise ValueError("Modular v1 coordinates require right-handed glTF Y up, +Z forward, meters.")

    @classmethod
    def from_dict(cls, value):
        fields(value, ("normalization", "units", "up_axis", "forward_axis", "handedness"),
               name="coordinates")
        return cls(**{**value, "normalization": NormalizationConvention.from_dict(value["normalization"])})

    def to_dict(self):
        return {"units": self.units, "up_axis": self.up_axis, "forward_axis": self.forward_axis,
                "handedness": self.handedness, "normalization": self.normalization.to_dict()}
