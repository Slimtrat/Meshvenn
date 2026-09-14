from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import bpy

from .constants import *
from .support import (
    _load_extension, _operator_available, _operator_callable,
    _operator_rna_class, _panel_rna_class, _parse_arguments,
    _purge_package_modules, _require, _require_close, _section,
    _ui_list_rna_class, _validate_package_tree,
)

# =========================================================
# SDF Blender properties
# =========================================================

def _validate_sdf_properties(
    settings,
) -> None:
    _section(
        "SDF Reconstruction V1 properties"
    )

    required = (
        "sdf_resolution",
        "sdf_symmetry_x",
        "sdf_smoothness",
        "sdf_surface_offset",
        "sdf_iso_level",
        "sdf_gradient_step_scale",
    )

    for name in required:
        _require(
            hasattr(
                settings,
                name,
            ),
            (
                "Missing SDF property: "
                f"{name}"
            ),
        )

    _require(
        settings.sdf_resolution
        == EXPECTED_SDF_RESOLUTION,
        (
            "Unexpected SDF "
            "resolution default."
        ),
    )

    _require(
        bool(
            settings.sdf_symmetry_x
        )
        == EXPECTED_SDF_SYMMETRY_X,
        (
            "Unexpected SDF "
            "symmetry default."
        ),
    )

    _require_close(
        settings.sdf_smoothness,
        EXPECTED_SDF_SMOOTHNESS,
        name="SDF smoothness",
    )

    _require_close(
        settings.sdf_surface_offset,
        EXPECTED_SDF_SURFACE_OFFSET,
        name="SDF surface offset",
    )

    _require_close(
        settings.sdf_iso_level,
        EXPECTED_SDF_ISO_LEVEL,
        name="SDF iso level",
    )

    _require_close(
        settings
        .sdf_gradient_step_scale,
        EXPECTED_SDF_GRADIENT_STEP_SCALE,
        name="SDF gradient step",
    )

    # -----------------------------------------------------
    # Check the UI safety cap of the current Python backend.
    # -----------------------------------------------------

    rna_property = (
        settings
        .bl_rna
        .properties[
            "sdf_resolution"
        ]
    )

    _require(
        int(
            rna_property.hard_min
        )
        == EXPECTED_SDF_MINIMUM_RESOLUTION,
        (
            "Unexpected SDF RNA "
            "minimum resolution."
        ),
    )

    _require(
        int(
            rna_property.hard_max
        )
        == EXPECTED_SDF_REFERENCE_MAX_RESOLUTION,
        (
            "Unexpected SDF RNA "
            "maximum resolution."
        ),
    )

    # -----------------------------------------------------
    # SDF and Native Visual Hull settings must remain
    # independent.
    # -----------------------------------------------------

    original_native_resolution = (
        settings.resolution
    )

    original_sdf_resolution = (
        settings.sdf_resolution
    )

    try:
        settings.resolution = 80
        settings.sdf_resolution = 64

        _require(
            settings.resolution == 80,
            (
                "Native Visual Hull resolution "
                "could not be changed."
            ),
        )

        _require(
            settings.sdf_resolution == 64,
            (
                "SDF resolution "
                "could not be changed."
            ),
        )

        _require(
            settings.resolution
            != settings.sdf_resolution,
            (
                "SDF and Visual Hull "
                "resolution settings are coupled."
            ),
        )

    finally:
        settings.resolution = (
            original_native_resolution
        )

        settings.sdf_resolution = (
            original_sdf_resolution
        )

    print(
        "SDF properties: OK"
    )

    print(
        (
            "  reference resolution: "
            f"{EXPECTED_SDF_RESOLUTION}³"
        )
    )

    print(
        (
            "  UI safety max: "
            f"{EXPECTED_SDF_REFERENCE_MAX_RESOLUTION}³"
        )
    )
