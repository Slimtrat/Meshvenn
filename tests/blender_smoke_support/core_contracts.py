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
# Generic GEOMETRY core
# =========================================================

def _validate_geometry_contract_core(
    package_name: str,
) -> None:
    _section(
        "generic GEOMETRY contract"
    )

    module = importlib.import_module(
        (
            f"{package_name}."
            "core.geometry_contracts"
        )
    )

    required_symbols = (
        "GeometryProjectionConvention",
        "GeometryProjectionSpace",
        "GeometrySurfaceOutput",
        "require_geometry_surface_output",
        "validate_geometry_surface_output",
    )

    for symbol in required_symbols:
        _require(
            hasattr(
                module,
                symbol,
            ),
            (
                "Generic GEOMETRY symbol "
                f"missing: {symbol}"
            ),
        )

    convention = (
        module
        .GeometryProjectionConvention
        .SURFACE_ENVELOPE_V1
    )

    _require(
        convention.value
        == EXPECTED_GEOMETRY_CONTRACT,
        (
            "Unexpected GEOMETRY "
            "projection convention."
        ),
    )

    projection_space = (
        module
        .GeometryProjectionSpace(
            width=16,
            depth=24,
            height=32,
            voxel_size=0.5,
            center_xy=True,
        )
    )

    _require(
        projection_space.dimensions
        == (
            16,
            24,
            32,
        ),
        (
            "Unexpected projection-space "
            "dimensions."
        ),
    )

    _require(
        projection_space
        .as_projection_kwargs()
        == {
            "width": 16,
            "depth": 24,
            "height": 32,
            "voxel_size": 0.5,
            "center_xy": True,
        },
        (
            "Projection-space arguments "
            "do not match MATERIAL contract."
        ),
    )

    _require(
        projection_space
        .minimum_local_point
        == (
            -4.0,
            -6.0,
            0.0,
        ),
        (
            "Unexpected minimum "
            "local bound."
        ),
    )

    _require(
        projection_space
        .maximum_local_point
        == (
            4.0,
            6.0,
            16.0,
        ),
        (
            "Unexpected maximum "
            "local bound."
        ),
    )

    print(
        "Generic GEOMETRY core: OK"
    )


# =========================================================
# SDF core
# =========================================================

def _validate_sdf_core(
    package_name: str,
) -> None:
    _section(
        "SDF core"
    )

    sdf_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.sdf"
            )
        )
    )

    surface_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.sdf_surface"
            )
        )
    )

    required_sdf_symbols = (
        "SignedDistanceMask",
        "SDFProjection",
        "SDFVolume",
        "SDFBuildConfig",
        "SDFBuildResult",
        "build_signed_distance_mask",
        "build_sdf_projections",
        "build_sdf_volume",
        "build_sdf_from_views",
        "fuse_signed_distances",
        "smooth_max",
    )

    for symbol in (
        required_sdf_symbols
    ):
        _require(
            hasattr(
                sdf_module,
                symbol,
            ),
            (
                "SDF core symbol "
                f"missing: {symbol}"
            ),
        )

    required_surface_symbols = (
        "SDFSurfaceConfig",
        "SDFSurfaceVertex",
        "SDFSurfaceMesh",
        "SDFSurfaceStats",
        "SDFSurfaceResult",
        "estimate_sdf_normal",
        "extract_surface_nets",
    )

    for symbol in (
        required_surface_symbols
    ):
        _require(
            hasattr(
                surface_module,
                symbol,
            ),
            (
                "SDF surface symbol "
                f"missing: {symbol}"
            ),
        )

    config = (
        sdf_module
        .cubic_sdf_config(
            16
        )
    )

    _require(
        config.dimensions
        == (
            16,
            16,
            16,
        ),
        (
            "Unexpected cubic "
            "SDF config."
        ),
    )

    _require(
        config.voxel_count
        == 4096,
        (
            "Unexpected SDF sample count."
        ),
    )

    surface_config = (
        surface_module
        .SDFSurfaceConfig()
    )

    surface_config.validate()

    _require_close(
        surface_config
        .gradient_step_scale,
        EXPECTED_SDF_GRADIENT_STEP_SCALE,
        name="SDF gradient step",
    )

    print(
        "SDF core import: OK"
    )

    print(
        "  signed distance field: OK"
    )

    print(
        "  continuous Surface Nets: OK"
    )


# =========================================================
# UV Bake core
# =========================================================

def _validate_uv_bake_core(
    package_name: str,
) -> None:
    _section(
        "UV Bake V2 core"
    )

    module = importlib.import_module(
        (
            f"{package_name}."
            "core.uv_bake"
        )
    )

    required_symbols = (
        "DEFAULT_TEXTURE_SIZE",
        "UVBakeVertex",
        "UVBakeTriangle",
        "UVBakeConfig",
        "UVBakeResult",
        "UVBakeStats",
        "TextureBuffer",
        "SurfaceColorSample",
        "bake_uv_texture",
        "square_texture_config",
        "texture_memory_bytes",
    )

    for symbol in required_symbols:
        _require(
            hasattr(
                module,
                symbol,
            ),
            (
                "UV Bake core symbol "
                f"missing: {symbol}"
            ),
        )

    _require(
        module.DEFAULT_TEXTURE_SIZE
        == EXPECTED_UV_BAKE_TEXTURE_SIZE_INT,
        (
            "Unexpected UV Bake "
            "core default."
        ),
    )

    default_config = (
        module.UVBakeConfig()
    )

    default_config.validate()

    _require(
        default_config.width
        == EXPECTED_UV_BAKE_TEXTURE_SIZE_INT,
        (
            "UVBakeConfig default width "
            "is out of sync."
        ),
    )

    _require(
        default_config.height
        == EXPECTED_UV_BAKE_TEXTURE_SIZE_INT,
        (
            "UVBakeConfig default height "
            "is out of sync."
        ),
    )

    explicit = (
        module.UVBakeConfig(
            width=8,
            height=8,
            padding_pixels=0,
            samples_per_axis=1,
        )
    )

    explicit.validate()

    _require(
        explicit.width == 8
        and explicit.height == 8,
        (
            "Explicit UV Bake size "
            "was overridden."
        ),
    )

    hq = (
        module
        .square_texture_config(
            1024
        )
    )

    _require(
        hq.width == 1024
        and hq.height == 1024,
        (
            "Explicit 1024 UV Bake "
            "mode unavailable."
        ),
    )

    print(
        "UV Bake V2 core import: OK"
    )
