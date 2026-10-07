"""Explicit height normalization; diagnostics are never coordinate authority."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

NATIVE_OBJECT_SCALE = "native-visual-hull-object-scale"
HISTORICAL_SOURCE = "historical-native-id-properties"


@dataclass(frozen=True)
class GeometryNormalization:
    normalized_height: bool
    target_height: float | None
    scale: float
    provenance: str

    def __post_init__(self):
        if type(self.normalized_height) is not bool:
            raise TypeError("Geometry normalized_height must be an explicit boolean.")
        if type(self.scale) not in (int, float) or not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("Geometry normalization scale must be finite and positive.")
        if self.provenance not in (NATIVE_OBJECT_SCALE, HISTORICAL_SOURCE):
            raise ValueError("Geometry normalization requires supported explicit provenance.")
        if self.normalized_height:
            if (type(self.target_height) not in (int, float) or not math.isfinite(self.target_height)
                    or self.target_height <= 0):
                raise ValueError("Height normalization requires a finite positive target_height.")
        elif self.target_height is not None or self.scale != 1:
            raise ValueError("Disabled height normalization requires null target_height and scale 1.")
        object.__setattr__(self, "scale", float(self.scale))
        if self.target_height is not None:
            object.__setattr__(self, "target_height", float(self.target_height))

    def to_dict(self):
        return {"normalized_height": self.normalized_height, "target_height": self.target_height,
                "scale": self.scale, "provenance": self.provenance}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping) or set(value) != {"normalized_height", "target_height", "scale", "provenance"}:
            raise ValueError("Invalid saved geometry normalization; prepare the source provenance explicitly.")
        return cls(**value)

    def validate_diagnostics(self, *mappings):
        """Reject contradictions, never reconstruct authority from old metrics."""
        expected = {"normalized_height": self.normalized_height, "target_height": self.target_height,
                    "normalization_scale": self.scale}
        for mapping in mappings:
            for key, actual in mapping.items():
                if key not in expected:
                    continue
                correct = actual == expected[key]
                if key == "normalized_height":
                    correct = type(actual) is bool and correct
                elif actual is not None:
                    correct = type(actual) in (int, float) and math.isfinite(actual) and correct
                if not correct:
                    raise ValueError(f"Diagnostic {key} contradicts explicit geometry normalization; repair its producer.")
