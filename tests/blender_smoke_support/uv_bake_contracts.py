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
# UV Bake properties
# =========================================================

def _validate_uv_bake_properties(
    settings,
) -> None:
    _section(
        "UV Bake V2 properties"
    )

    required = (
        "uv_bake_texture_size",
        "uv_bake_padding_pixels",
        "uv_bake_samples_per_axis",
        "uv_bake_reuse_existing_uv",
        "uv_bake_uv_layer_name",
        "uv_bake_island_margin",
        "uv_bake_angle_limit_degrees",
    )

    for name in required:
        _require(
            hasattr(
                settings,
                name,
            ),
            (
                "Missing UV Bake property: "
                f"{name}"
            ),
        )

    _require(
        settings.uv_bake_texture_size
        == EXPECTED_UV_BAKE_TEXTURE_SIZE,
        (
            "Unexpected UV Bake "
            "texture default."
        ),
    )

    _require(
        settings.uv_bake_padding_pixels
        == EXPECTED_UV_BAKE_PADDING_PIXELS,
        (
            "Unexpected UV Bake "
            "padding default."
        ),
    )

    _require(
        settings.uv_bake_samples_per_axis
        == EXPECTED_UV_BAKE_SAMPLES_PER_AXIS,
        (
            "Unexpected UV Bake "
            "sample default."
        ),
    )

    _require(
        settings.uv_bake_uv_layer_name
        == EXPECTED_UV_BAKE_UV_LAYER_NAME,
        (
            "Unexpected UV Bake "
            "UV layer default."
        ),
    )

    _require(
        bool(
            settings
            .uv_bake_reuse_existing_uv
        )
        == EXPECTED_UV_BAKE_REUSE_EXISTING_UV,
        (
            "Unexpected Reuse Existing UV "
            "default."
        ),
    )

    _require_close(
        settings.uv_bake_island_margin,
        EXPECTED_UV_BAKE_ISLAND_MARGIN,
        name="UV Bake island margin",
    )

    _require_close(
        settings
        .uv_bake_angle_limit_degrees,
        EXPECTED_UV_BAKE_ANGLE_LIMIT_DEGREES,
        name="UV Bake angle limit",
    )

    for value in (
        "1024",
        "2048",
        "4096",
    ):
        settings.uv_bake_texture_size = (
            value
        )

        _require(
            settings.uv_bake_texture_size
            == value,
            (
                "UV Bake EnumProperty "
                f"rejected {value}."
            ),
        )

    settings.uv_bake_texture_size = (
        EXPECTED_UV_BAKE_TEXTURE_SIZE
    )

    print(
        "UV Bake V2 properties: OK"
    )


# =========================================================
# UV Bake alignment
# =========================================================

def _validate_uv_bake_default_alignment(
    package_name: str,
    settings,
) -> None:
    _section(
        "UV Bake default alignment"
    )

    core_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.uv_bake"
            )
        )
    )

    implementation_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations.uv_bake"
            )
        )
    )

    properties_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "properties"
            )
        )
    )

    expected_int = (
        EXPECTED_UV_BAKE_TEXTURE_SIZE_INT
    )

    _require(
        core_module.DEFAULT_TEXTURE_SIZE
        == expected_int,
        (
            "core.uv_bake default "
            "is out of sync."
        ),
    )

    _require(
        implementation_module.DEFAULT_TEXTURE_SIZE
        == expected_int,
        (
            "UV Bake implementation "
            "default is out of sync."
        ),
    )

    _require(
        properties_module
        .DEFAULT_UV_BAKE_TEXTURE_SIZE
        == EXPECTED_UV_BAKE_TEXTURE_SIZE,
        (
            "UV Bake property default "
            "is out of sync."
        ),
    )

    material_config = (
        implementation_module
        .UVBakeMaterialConfig()
    )

    bake_config = (
        material_config
        .to_bake_config()
    )

    _require(
        bake_config.width
        == expected_int
        and bake_config.height
        == expected_int,
        (
            "UV Bake config conversion "
            "is out of sync."
        ),
    )

    _require_close(
        material_config
        .effective_island_margin_pixels,
        EXPECTED_SMART_PROJECT_MARGIN_PIXELS,
        name=(
            "UV Bake Smart Project "
            "margin"
        ),
    )

    _require(
        settings.uv_bake_texture_size
        == EXPECTED_UV_BAKE_TEXTURE_SIZE,
        (
            "Scene UV Bake default "
            "is out of sync."
        ),
    )

    print(
        "UV Bake defaults aligned: OK"
    )
