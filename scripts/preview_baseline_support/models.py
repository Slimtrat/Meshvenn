from __future__ import annotations

import argparse
import hashlib
import json
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

SCHEMA_VERSION = 1

DEFAULT_RENDERER_VERSION = 1

DEFAULT_OUTPUTS = {
    "geometry": "geometry.png",
    "material": "material.png",
    "turntable": "turntable.png",
}


# ---------------------------------------------------------
# Errors
# ---------------------------------------------------------

class BaselineError(RuntimeError):
    pass


# ---------------------------------------------------------
# Data
# ---------------------------------------------------------

@dataclass(frozen=True)
class BaselineConfig:
    resolution: int

    mesh_mode: str
    material_mode: str

    samples: int

    turntable_views: int
    render_size: int

    renderer_version: int = (
        DEFAULT_RENDERER_VERSION
    )

    def validate(self) -> None:
        if self.resolution <= 0:
            raise BaselineError(
                "resolution must be greater than zero."
            )

        if self.mesh_mode not in {
            "blocks",
            "surface_nets",
        }:
            raise BaselineError(
                (
                    "Unsupported mesh mode: "
                    f"{self.mesh_mode}"
                )
            )

        if not self.material_mode:
            raise BaselineError(
                "material_mode cannot be empty."
            )

        if self.samples <= 0:
            raise BaselineError(
                "samples must be greater than zero."
            )

        if self.turntable_views <= 0:
            raise BaselineError(
                (
                    "turntable_views must be "
                    "greater than zero."
                )
            )

        if self.render_size <= 0:
            raise BaselineError(
                (
                    "render_size must be "
                    "greater than zero."
                )
            )

        if self.renderer_version <= 0:
            raise BaselineError(
                (
                    "renderer_version must be "
                    "greater than zero."
                )
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        return {
            "resolution": self.resolution,
            "mesh_mode": self.mesh_mode,
            "material_mode": self.material_mode,
            "samples": self.samples,
            "turntable_views": (
                self.turntable_views
            ),
            "render_size": self.render_size,
            "renderer_version": (
                self.renderer_version
            ),
        }


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    reason: str


# ---------------------------------------------------------
# Hashing
# ---------------------------------------------------------
