from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

from scripts.render_turntable import look_at, setup_render

def common_ortho_scale(
    model_size: Vector,
    cells: list[
        tuple[
            str,
            float,
            float,
            tuple[
                int,
                int,
                int,
                int,
            ],
        ]
    ],
    *,
    framing: float,
) -> float:
    if framing <= 0.0:
        raise ValueError(
            "framing must be greater than zero"
        )

    minimum_aspect = float(
        "inf"
    )

    for (
        _name,
        _azimuth,
        _elevation,
        bbox,
    ) in cells:
        (
            x0,
            y0,
            x1,
            y1,
        ) = bbox

        width = (
            x1
            - x0
        )

        height = (
            y1
            - y0
        )

        aspect = (
            width
            / height
        )

        minimum_aspect = min(
            minimum_aspect,
            aspect,
        )

    horizontal_max = math.hypot(
        model_size.x,
        model_size.y,
    )

    horizontal_views_scale = max(
        model_size.z,
        (
            horizontal_max
            / minimum_aspect
        ),
    )

    top_bottom_scale = max(
        model_size.x,
        model_size.y,
        (
            model_size.x
            / minimum_aspect
        ),
        (
            model_size.y
            / minimum_aspect
        ),
    )

    return (
        max(
            horizontal_views_scale,
            top_bottom_scale,
            0.01,
        )
        * framing
    )


# ---------------------------------------------------------
# Camera positioning
# ---------------------------------------------------------

def place_projection_camera(
    camera: bpy.types.Object,
    *,
    target: Vector,
    model_size: Vector,
    azimuth_degrees: float,
    elevation_degrees: float,
    ortho_scale: float,
) -> None:
    framing_size = max(
        model_size.x,
        model_size.y,
        model_size.z,
        0.01,
    )

    distance = (
        framing_size
        * 4.0
    )

    azimuth = math.radians(
        azimuth_degrees
    )

    elevation = math.radians(
        elevation_degrees
    )

    horizontal_distance = (
        math.cos(
            elevation
        )
        * distance
    )

    camera.location = (
        math.sin(
            azimuth
        )
        * horizontal_distance,
        -math.cos(
            azimuth
        )
        * horizontal_distance,
        math.sin(
            elevation
        )
        * distance,
    )

    look_at(
        camera,
        target,
    )

    camera.data.ortho_scale = (
        ortho_scale
    )


# ---------------------------------------------------------
# Render configuration
# ---------------------------------------------------------

def configure_projection_render(
    *,
    samples: int,
) -> None:
    # Reuse the existing visual-preview
    # renderer configuration.
    setup_render(
        size=256,
        samples=samples,
    )

    scene = (
        bpy.context.scene
    )

    # Projection-sheet renders need alpha because
    # they are composited into the original sheet.
    scene.render.film_transparent = (
        True
    )

    scene.render.image_settings.color_mode = (
        "RGBA"
    )


# ---------------------------------------------------------
# Render one view
# ---------------------------------------------------------
