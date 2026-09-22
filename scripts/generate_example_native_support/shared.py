from __future__ import annotations

import argparse
import hashlib
import json
import sys

from array import array
from dataclasses import dataclass
from pathlib import Path

import bpy

from mathutils import Matrix


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.image_mask import BinaryMask
from core.native_bridge import NativeProjection
from core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from core.native_scan import NativeScanner
from core.presheet_layout import (
    CELL_SPECS,
    pixel_bbox,
)
from core.projected_material import (
    BLEND_MODE,
    COLOR_ATTRIBUTE_NAME,
    MATERIAL_MODE,
    VISIBILITY_MODE,
    ProjectedMaterialView,
    apply_projected_material,
)
from scripts.run_logger import RunLogger


# ---------------------------------------------------------
# Data
# ---------------------------------------------------------

@dataclass(frozen=True)
class ExtractedView:
    name: str
    path: Path

    azimuth_degrees: float
    elevation_degrees: float

    bbox: tuple[
        int,
        int,
        int,
        int,
    ]

    sha256: str

    valid: bool

    mask: BinaryMask
