from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import Any

import bpy

from .constants import *
from .support import (_clamp01, _purge_package_modules, _quantize_unorm8, _require, _require_close, _require_rgba8_close, _section)

# =========================================================
# Blender mesh -> UVBakeTriangle
# =========================================================

def _validate_triangle_adapter(
    implementation_module,
    obj,
    uv_layer,
):
    _section(
        "Blender → UVBakeTriangle"
    )

    triangles = (
        implementation_module
        ._build_uv_triangles(
            obj,
            uv_layer,
        )
    )

    _require(
        len(
            triangles
        )
        == 2,
        (
            "Expected exactly two "
            "UV bake triangles."
        ),
    )

    for (
        triangle_index,
        triangle,
    ) in enumerate(
        triangles
    ):
        _require(
            triangle.absolute_uv_area
            > 0.0,
            (
                "Triangle has zero UV area: "
                f"{triangle_index}"
            ),
        )

        for vertex in (
            triangle.a,
            triangle.b,
            triangle.c,
        ):
            (
                x,
                y,
                z,
            ) = (
                vertex.position
            )

            (
                u,
                v,
            ) = (
                vertex.uv
            )

            _require_close(
                x,
                u,
                message=(
                    "Position X / UV U mismatch."
                ),
            )

            _require_close(
                y,
                v,
                message=(
                    "Position Y / UV V mismatch."
                ),
            )

            _require_close(
                z,
                0.0,
                message=(
                    "Unexpected surface Z."
                ),
            )

            (
                nx,
                ny,
                nz,
            ) = (
                vertex.normal
            )

            _require_close(
                nx,
                0.0,
                message=(
                    "Unexpected normal X."
                ),
            )

            _require_close(
                ny,
                0.0,
                message=(
                    "Unexpected normal Y."
                ),
            )

            _require_close(
                nz,
                1.0,
                message=(
                    "Unexpected normal Z."
                ),
            )

    print(
        "Triangle adapter: OK"
    )

    return triangles
