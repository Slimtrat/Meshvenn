from __future__ import annotations

import argparse
import importlib
import math
import sys
import traceback

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import bpy


# =========================================================
# Configuration
# =========================================================

DEFAULT_PACKAGE_ROOT = (
    Path("dist")
    / "blender_projection_tool"
)


REQUIRED_PACKAGE_FILES = (
    "__init__.py",
    "blender_manifest.toml",
    "properties.py",
    "operators.py",
    "ui.py",
    "version.py",
    "translations.py",

    # -----------------------------------------------------
    # Core
    # -----------------------------------------------------

    "core/__init__.py",

    "core/pipeline_contracts.py",
    "core/pipeline_registry.py",
    "core/pipeline_runner.py",

    # Generic GEOMETRY contract
    "core/geometry_contracts.py",

    "core/image_mask.py",

    "core/native_loader.py",
    "core/native_bridge.py",
    "core/native_mesh_builder.py",
    "core/native_scan.py",

    "core/projection_math.py",

    "core/projected_material.py",
    "core/material_visibility.py",
    "core/material_blend.py",

    "core/uv_bake.py",

    # -----------------------------------------------------
    # Implementations
    # -----------------------------------------------------

    "implementations/__init__.py",

    "implementations/projection_images.py",
    "implementations/native_visual_hull.py",

    "implementations/projected_color.py",
    "implementations/uv_bake.py",

    # -----------------------------------------------------
    # Native binaries
    # -----------------------------------------------------

    "native/bin/libbpt_core.so",
    "native/bin/bpt_core.dll",
)


EXPECTED_IMPLEMENTATIONS = (
    "projection-images",
    "native-visual-hull",
    "projected-color-v1.2",
    "uv-bake-v2",
)


EXPECTED_PROJECTION_NAMES = (
    "Front",
    "Right",
    "Back",
    "Top",
)


# =========================================================
# UV Bake expected defaults
# =========================================================

EXPECTED_UV_BAKE_TEXTURE_SIZE = (
    "512"
)

EXPECTED_UV_BAKE_TEXTURE_SIZE_INT = (
    int(
        EXPECTED_UV_BAKE_TEXTURE_SIZE
    )
)

EXPECTED_UV_BAKE_PADDING_PIXELS = 8

EXPECTED_UV_BAKE_SAMPLES_PER_AXIS = (
    "1"
)

EXPECTED_UV_BAKE_UV_LAYER_NAME = (
    "MeshvennUV"
)

EXPECTED_UV_BAKE_ISLAND_MARGIN = (
    0.02
)

EXPECTED_UV_BAKE_ANGLE_LIMIT_DEGREES = (
    66.0
)

EXPECTED_UV_BAKE_REUSE_EXISTING_UV = (
    False
)

EXPECTED_SMART_PROJECT_MARGIN_PIXELS = (
    0.5
)


# =========================================================
# Generic GEOMETRY expected values
# =========================================================

EXPECTED_GEOMETRY_CONTRACT = (
    "surface-envelope-v1"
)

FAKE_GEOMETRY_IMPLEMENTATION_ID = (
    "sdf-reconstruction-v1"
)


# =========================================================
# Blender RNA identifiers
# =========================================================

EXPECTED_OPERATOR_RNA_IDS = (
    "BPT_OT_load_projection_image",
    "BPT_OT_import_turntable_images",
    "BPT_OT_add_projection",
    "BPT_OT_remove_projection",
    "BPT_OT_add_turntable_preset",
    "BPT_OT_add_front_side_preset",

    "BPT_OT_set_pipeline_implementation",
    "BPT_OT_reset_pipeline_settings",

    "BPT_OT_run_pipeline",
    "BPT_OT_run_pipeline_stage",

    "BPT_OT_generate_character",
)


EXPECTED_OPERATOR_IDNAMES = (
    "bpt.load_projection_image",
    "bpt.import_turntable_images",
    "bpt.add_projection",
    "bpt.remove_projection",
    "bpt.add_turntable_preset",
    "bpt.add_front_side_preset",

    "bpt.set_pipeline_implementation",
    "bpt.reset_pipeline_settings",

    "bpt.run_pipeline",
    "bpt.run_pipeline_stage",

    "bpt.generate_character",
)


MAIN_PANEL_RNA_ID = (
    "BPT_PT_main_panel"
)

PROJECTION_UI_LIST_RNA_ID = (
    "BPT_UL_ProjectionViews"
)


# =========================================================
# CLI
# =========================================================

def _script_arguments() -> list[str]:
    if "--" not in sys.argv:
        return []

    separator_index = (
        sys.argv.index(
            "--"
        )
    )

    return sys.argv[
        separator_index + 1:
    ]


def _parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test the packaged "
            "Meshvenn Blender extension."
        )
    )

    parser.add_argument(
        "--package-root",
        default=str(
            DEFAULT_PACKAGE_ROOT
        ),
        help=(
            "Path to the unpacked Blender "
            "extension package."
        ),
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Generic helpers
# =========================================================

def _section(
    title: str,
) -> None:
    print()

    print(
        "=" * 72
    )

    print(
        f"Meshvenn smoke | {title}"
    )

    print(
        "=" * 72
    )


def _require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def _require_close(
    actual: float,
    expected: float,
    *,
    name: str,
    tolerance: float = 1e-6,
) -> None:
    if not math.isclose(
        float(
            actual
        ),
        float(
            expected
        ),
        rel_tol=tolerance,
        abs_tol=tolerance,
    ):
        raise AssertionError(
            (
                f"Unexpected {name}.\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )
        )


def _purge_package_modules(
    package_name: str,
) -> None:
    prefix = (
        package_name
        + "."
    )

    names = [
        name
        for name
        in tuple(
            sys.modules.keys()
        )
        if (
            name == package_name
            or name.startswith(
                prefix
            )
        )
    ]

    for name in sorted(
        names,
        key=len,
        reverse=True,
    ):
        sys.modules.pop(
            name,
            None,
        )


# =========================================================
# RNA lookup helpers
# =========================================================

def _operator_rna_class(
    identifier: str,
):
    return (
        bpy.types.Operator
        .bl_rna_get_subclass_py(
            identifier
        )
    )


def _panel_rna_class(
    identifier: str,
):
    return (
        bpy.types.Panel
        .bl_rna_get_subclass_py(
            identifier
        )
    )


def _ui_list_rna_class(
    identifier: str,
):
    return (
        bpy.types.UIList
        .bl_rna_get_subclass_py(
            identifier
        )
    )


def _operator_callable(
    idname: str,
):
    namespace_name, operator_name = (
        idname.split(
            ".",
            1,
        )
    )

    namespace = getattr(
        bpy.ops,
        namespace_name,
    )

    return getattr(
        namespace,
        operator_name,
    )


def _operator_available(
    idname: str,
) -> bool:
    try:
        operator = (
            _operator_callable(
                idname
            )
        )

        operator.get_rna_type()

        return True

    except Exception:
        return False


# =========================================================
# Package tree
# =========================================================

def _validate_package_tree(
    package_root: Path,
) -> None:
    _section(
        "package tree"
    )

    _require(
        package_root.is_dir(),
        (
            "Package directory does not exist: "
            f"{package_root}"
        ),
    )

    missing: list[str] = []

    for relative_path in (
        REQUIRED_PACKAGE_FILES
    ):
        path = (
            package_root
            / relative_path
        )

        if not path.is_file():
            missing.append(
                relative_path
            )

    if missing:
        formatted = "\n".join(
            f"  - {path}"
            for path
            in missing
        )

        raise AssertionError(
            (
                "Packaged Meshvenn extension "
                "is incomplete.\n"
                "Missing files:\n"
                f"{formatted}"
            )
        )

    print(
        "Package tree: OK"
    )

    for relative_path in (
        REQUIRED_PACKAGE_FILES
    ):
        print(
            f"  OK  {relative_path}"
        )


# =========================================================
# Extension import
# =========================================================

def _load_extension(
    package_root: Path,
):
    _section(
        "import extension"
    )

    package_root = (
        package_root.resolve()
    )

    package_parent = (
        package_root.parent
    )

    package_name = (
        package_root.name
    )

    _purge_package_modules(
        package_name
    )

    package_parent_string = str(
        package_parent
    )

    if (
        package_parent_string
        not in sys.path
    ):
        sys.path.insert(
            0,
            package_parent_string,
        )

    print(
        f"Package root: {package_root}"
    )

    print(
        f"Module name: {package_name}"
    )

    module = (
        importlib.import_module(
            package_name
        )
    )

    _require(
        callable(
            getattr(
                module,
                "register",
                None,
            )
        ),
        (
            "Extension does not expose "
            "register()."
        ),
    )

    _require(
        callable(
            getattr(
                module,
                "unregister",
                None,
            )
        ),
        (
            "Extension does not expose "
            "unregister()."
        ),
    )

    print(
        "Import: OK"
    )

    return (
        module,
        package_name,
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

    module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.geometry_contracts"
            )
        )
    )

    required_symbols = (
        "GeometryProjectionConvention",
        "GeometryProjectionSpace",
        "GeometrySurfaceOutput",
        "require_geometry_surface_output",
        "validate_geometry_surface_output",
    )

    for symbol in (
        required_symbols
    ):
        _require(
            hasattr(
                module,
                symbol,
            ),
            (
                "Generic GEOMETRY symbol "
                "missing from packaged "
                "extension: "
                f"{symbol}"
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
            "Unexpected generic projection "
            "coordinate convention.\n"
            f"Expected: "
            f"{EXPECTED_GEOMETRY_CONTRACT}\n"
            f"Actual:   "
            f"{convention.value}"
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
            "Unexpected GeometryProjectionSpace "
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
            "GeometryProjectionSpace does not "
            "produce the projection arguments "
            "expected by MATERIAL."
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
            "Unexpected generic GEOMETRY "
            "minimum local bound."
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
            "Unexpected generic GEOMETRY "
            "maximum local bound."
        ),
    )

    print(
        "Generic GEOMETRY core: OK"
    )

    print(
        (
            "  convention: "
            f"{convention.value}"
        )
    )

    print(
        (
            "  dimensions: "
            f"{projection_space.dimensions}"
        )
    )


# =========================================================
# Core UV Bake
# =========================================================

def _validate_uv_bake_core(
    package_name: str,
) -> None:
    _section(
        "UV Bake V2 core"
    )

    module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.uv_bake"
            )
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

    for symbol in (
        required_symbols
    ):
        _require(
            hasattr(
                module,
                symbol,
            ),
            (
                "UV Bake core symbol missing: "
                f"{symbol}"
            ),
        )

    _require(
        module.DEFAULT_TEXTURE_SIZE
        == EXPECTED_UV_BAKE_TEXTURE_SIZE_INT,
        (
            "Unexpected core UV Bake "
            "texture-size default.\n"
            f"Expected: "
            f"{EXPECTED_UV_BAKE_TEXTURE_SIZE_INT}\n"
            f"Actual:   "
            f"{module.DEFAULT_TEXTURE_SIZE}"
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
            "does not match product default."
        ),
    )

    _require(
        default_config.height
        == EXPECTED_UV_BAKE_TEXTURE_SIZE_INT,
        (
            "UVBakeConfig default height "
            "does not match product default."
        ),
    )

    explicit_config = (
        module.UVBakeConfig(
            width=8,
            height=8,
            padding_pixels=0,
            samples_per_axis=1,
        )
    )

    explicit_config.validate()

    _require(
        explicit_config.width == 8,
        (
            "Explicit UV Bake width "
            "was unexpectedly overridden."
        ),
    )

    _require(
        explicit_config.height == 8,
        (
            "Explicit UV Bake height "
            "was unexpectedly overridden."
        ),
    )

    high_quality_config = (
        module.square_texture_config(
            1024
        )
    )

    _require(
        high_quality_config.width
        == 1024,
        (
            "Explicit 1024 UV Bake mode "
            "is no longer available."
        ),
    )

    _require(
        high_quality_config.height
        == 1024,
        (
            "Explicit 1024 UV Bake mode "
            "is no longer available."
        ),
    )

    _require(
        module.texture_memory_bytes(
            1024,
            1024,
        )
        == (
            1024
            * 1024
            * 4
            * 4
        ),
        (
            "UV Bake texture memory helper "
            "returned an unexpected result."
        ),
    )

    print(
        "UV Bake V2 core import: OK"
    )

    print(
        (
            "  default texture: "
            f"{module.DEFAULT_TEXTURE_SIZE}²"
        )
    )

    print(
        "  explicit 1024²: available"
    )


# =========================================================
# Scene / properties
# =========================================================

def _validate_scene_properties(
    package_name: str,
) -> Any:
    _section(
        "scene properties"
    )

    _require(
        hasattr(
            bpy.types.Scene,
            "bpt_settings",
        ),
        (
            "Scene.bpt_settings "
            "was not registered."
        ),
    )

    scene = (
        bpy.context.scene
    )

    _require(
        scene is not None,
        (
            "No active Blender scene "
            "is available."
        ),
    )

    settings = getattr(
        scene,
        "bpt_settings",
        None,
    )

    _require(
        settings is not None,
        (
            "Active scene does not expose "
            "bpt_settings."
        ),
    )

    properties_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "properties"
            )
        )
    )

    properties_module.ensure_scene_defaults(
        scene
    )

    print(
        "Scene.bpt_settings: OK"
    )

    return settings


# =========================================================
# Projection defaults
# =========================================================

def _validate_projection_defaults(
    settings,
) -> None:
    _section(
        "projection defaults"
    )

    actual_names = tuple(
        projection.name
        for projection
        in settings.projections
    )

    _require(
        actual_names
        == EXPECTED_PROJECTION_NAMES,
        (
            "Unexpected default projections.\n"
            f"Expected: "
            f"{EXPECTED_PROJECTION_NAMES}\n"
            f"Actual:   {actual_names}"
        ),
    )

    print(
        "Default projections: OK"
    )

    for name in actual_names:
        print(
            f"  OK  {name}"
        )


# =========================================================
# Pipeline defaults
# =========================================================

def _validate_pipeline_defaults(
    settings,
) -> None:
    _section(
        "pipeline defaults"
    )

    pipeline = (
        settings.pipeline
    )

    _require(
        bool(
            pipeline.initialized
        ),
        (
            "Pipeline defaults were not "
            "initialized."
        ),
    )

    expected_ids = (
        (
            pipeline
            .input_stage
            .implementation_id,
            "projection-images",
            "INPUT",
        ),
        (
            pipeline
            .geometry_stage
            .implementation_id,
            "native-visual-hull",
            "GEOMETRY",
        ),
        (
            pipeline
            .material_stage
            .implementation_id,
            "projected-color-v1.2",
            "MATERIAL",
        ),
    )

    for (
        actual,
        expected,
        stage_name,
    ) in expected_ids:
        _require(
            actual == expected,
            (
                f"Unexpected {stage_name} "
                "default implementation.\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            ),
        )

    _require(
        pipeline.input_stage.enabled,
        (
            "INPUT must be enabled "
            "by default."
        ),
    )

    _require(
        pipeline.geometry_stage.enabled,
        (
            "GEOMETRY must be enabled "
            "by default."
        ),
    )

    _require(
        pipeline.material_stage.enabled,
        (
            "MATERIAL must be enabled "
            "by default."
        ),
    )

    _require(
        not pipeline.rig_stage.enabled,
        (
            "RIG must be disabled "
            "by default."
        ),
    )

    _require(
        not pipeline.export_stage.enabled,
        (
            "EXPORT must be disabled "
            "by default."
        ),
    )

    print(
        "Pipeline defaults: OK"
    )

    print(
        "  INPUT    projection-images"
    )

    print(
        "  GEOMETRY native-visual-hull"
    )

    print(
        "  MATERIAL projected-color-v1.2"
    )

    print(
        (
            "            uv-bake-v2 "
            "available but not default"
        )
    )

    print(
        "  RIG      disabled"
    )

    print(
        "  EXPORT   disabled"
    )


# =========================================================
# UV Bake Blender properties
# =========================================================

def _validate_uv_bake_properties(
    settings,
) -> None:
    _section(
        "UV Bake V2 properties"
    )

    required_properties = (
        "uv_bake_texture_size",
        "uv_bake_padding_pixels",
        "uv_bake_samples_per_axis",
        "uv_bake_reuse_existing_uv",
        "uv_bake_uv_layer_name",
        "uv_bake_island_margin",
        "uv_bake_angle_limit_degrees",
    )

    for property_name in (
        required_properties
    ):
        _require(
            hasattr(
                settings,
                property_name,
            ),
            (
                "Missing UV Bake property: "
                f"{property_name}"
            ),
        )

    _require(
        settings.uv_bake_texture_size
        == EXPECTED_UV_BAKE_TEXTURE_SIZE,
        (
            "Unexpected UV Bake texture "
            "size default.\n"
            f"Expected: "
            f"{EXPECTED_UV_BAKE_TEXTURE_SIZE}\n"
            f"Actual:   "
            f"{settings.uv_bake_texture_size}"
        ),
    )

    _require(
        settings.uv_bake_padding_pixels
        == EXPECTED_UV_BAKE_PADDING_PIXELS,
        (
            "Unexpected UV Bake padding "
            "default."
        ),
    )

    _require(
        settings.uv_bake_samples_per_axis
        == EXPECTED_UV_BAKE_SAMPLES_PER_AXIS,
        (
            "Unexpected UV Bake supersampling "
            "default."
        ),
    )

    _require(
        settings.uv_bake_uv_layer_name
        == EXPECTED_UV_BAKE_UV_LAYER_NAME,
        (
            "Unexpected UV Bake UV layer "
            "name default."
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
        settings
        .uv_bake_island_margin,
        EXPECTED_UV_BAKE_ISLAND_MARGIN,
        name=(
            "UV Bake island margin"
        ),
    )

    _require_close(
        settings
        .uv_bake_angle_limit_degrees,
        EXPECTED_UV_BAKE_ANGLE_LIMIT_DEGREES,
        name=(
            "UV Bake angle limit"
        ),
    )

    # -----------------------------------------------------
    # Higher-quality modes remain selectable.
    # -----------------------------------------------------

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
                "UV Bake texture-size "
                "EnumProperty rejected "
                f"{value}."
            ),
        )

    settings.uv_bake_texture_size = (
        EXPECTED_UV_BAKE_TEXTURE_SIZE
    )

    settings.uv_bake_samples_per_axis = (
        "2"
    )

    _require(
        settings.uv_bake_samples_per_axis
        == "2",
        (
            "UV Bake samples EnumProperty "
            "could not be changed."
        ),
    )

    settings.uv_bake_samples_per_axis = (
        EXPECTED_UV_BAKE_SAMPLES_PER_AXIS
    )

    print(
        "UV Bake V2 properties: OK"
    )

    print(
        (
            "  default: "
            f"{EXPECTED_UV_BAKE_TEXTURE_SIZE}²"
        )
    )

    print(
        "  HQ:      1024² / 2048² / 4096²"
    )


# =========================================================
# UV Bake default alignment
# =========================================================

def _validate_uv_bake_default_alignment(
    package_name: str,
    settings,
) -> None:
    """
    Prevent four independent surfaces from drifting apart:

        pure core
        Blender implementation
        Blender property definition
        instantiated scene RNA
    """

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

    expected_string = (
        EXPECTED_UV_BAKE_TEXTURE_SIZE
    )

    _require(
        core_module.DEFAULT_TEXTURE_SIZE
        == expected_int,
        (
            "core.uv_bake DEFAULT_TEXTURE_SIZE "
            "is out of sync.\n"
            f"Expected: {expected_int}\n"
            f"Actual:   "
            f"{core_module.DEFAULT_TEXTURE_SIZE}"
        ),
    )

    _require(
        implementation_module.DEFAULT_TEXTURE_SIZE
        == expected_int,
        (
            "implementations.uv_bake "
            "DEFAULT_TEXTURE_SIZE is out of sync.\n"
            f"Expected: {expected_int}\n"
            f"Actual:   "
            f"{implementation_module.DEFAULT_TEXTURE_SIZE}"
        ),
    )

    _require(
        properties_module
        .DEFAULT_UV_BAKE_TEXTURE_SIZE
        == expected_string,
        (
            "properties.py UV Bake default "
            "is out of sync.\n"
            f"Expected: {expected_string!r}\n"
            "Actual:   "
            f"{properties_module.DEFAULT_UV_BAKE_TEXTURE_SIZE!r}"
        ),
    )

    core_config = (
        core_module.UVBakeConfig()
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
        core_config.width
        == expected_int,
        (
            "Core UVBakeConfig width "
            "is out of sync."
        ),
    )

    _require(
        core_config.height
        == expected_int,
        (
            "Core UVBakeConfig height "
            "is out of sync."
        ),
    )

    _require(
        material_config.texture_size
        == expected_int,
        (
            "UVBakeMaterialConfig default "
            "is out of sync."
        ),
    )

    _require(
        bake_config.width
        == expected_int,
        (
            "UVBakeMaterialConfig.to_bake_config() "
            "has wrong width."
        ),
    )

    _require(
        bake_config.height
        == expected_int,
        (
            "UVBakeMaterialConfig.to_bake_config() "
            "has wrong height."
        ),
    )

    _require(
        settings.uv_bake_texture_size
        == expected_string,
        (
            "Instantiated Blender scene setting "
            "is out of sync."
        ),
    )

    _require_close(
        material_config
        .effective_island_margin_pixels,
        EXPECTED_SMART_PROJECT_MARGIN_PIXELS,
        name=(
            "effective Smart Project "
            "margin in pixels"
        ),
    )

    expected_fraction = (
        EXPECTED_SMART_PROJECT_MARGIN_PIXELS
        / float(
            expected_int
        )
    )

    _require_close(
        material_config
        .effective_island_margin_fraction,
        expected_fraction,
        name=(
            "effective Smart Project "
            "margin fraction"
        ),
    )

    print(
        "UV Bake defaults aligned: OK"
    )

    print(
        (
            "  core:           "
            f"{core_module.DEFAULT_TEXTURE_SIZE}"
        )
    )

    print(
        (
            "  implementation: "
            f"{implementation_module.DEFAULT_TEXTURE_SIZE}"
        )
    )

    print(
        (
            "  properties:     "
            f"{properties_module.DEFAULT_UV_BAKE_TEXTURE_SIZE}"
        )
    )

    print(
        (
            "  scene RNA:      "
            f"{settings.uv_bake_texture_size}"
        )
    )

    print(
        (
            "  Smart margin:   "
            f"{material_config.effective_island_margin_pixels:.2f}px"
        )
    )


# =========================================================
# Registry
# =========================================================

def _validate_registry(
    package_name: str,
) -> None:
    _section(
        "pipeline registry"
    )

    registry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_registry"
            )
        )
    )

    contracts_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_contracts"
            )
        )
    )

    registry = (
        registry_module
        .PIPELINE_REGISTRY
    )

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    actual_ids = (
        registry
        .implementation_ids()
    )

    _require(
        actual_ids
        == EXPECTED_IMPLEMENTATIONS,
        (
            "Unexpected registered "
            "implementations.\n"
            f"Expected: "
            f"{EXPECTED_IMPLEMENTATIONS}\n"
            f"Actual:   {actual_ids}"
        ),
    )

    expected_defaults = {
        PipelineStage.INPUT:
            "projection-images",

        PipelineStage.GEOMETRY:
            "native-visual-hull",

        PipelineStage.MATERIAL:
            "projected-color-v1.2",

        PipelineStage.RIG:
            None,

        PipelineStage.EXPORT:
            None,
    }

    for (
        stage,
        expected,
    ) in (
        expected_defaults.items()
    ):
        actual = (
            registry.default_id(
                stage
            )
        )

        _require(
            actual == expected,
            (
                "Unexpected registry default "
                f"for {stage.value}.\n"
                f"Expected: {expected!r}\n"
                f"Actual:   {actual!r}"
            ),
        )

    uv_bake = (
        registry.require(
            "uv-bake-v2",
            stage=(
                PipelineStage.MATERIAL
            ),
        )
    )

    descriptor = (
        uv_bake.descriptor
    )

    _require(
        descriptor.identifier
        == "uv-bake-v2",
        (
            "Unexpected UV Bake "
            "implementation identifier."
        ),
    )

    _require(
        descriptor.stage
        == PipelineStage.MATERIAL,
        (
            "UV Bake V2 must belong "
            "to MATERIAL stage."
        ),
    )

    _require(
        descriptor.label
        == "UV Bake V2",
        (
            "Unexpected UV Bake "
            "V2 label."
        ),
    )

    _require(
        descriptor.experimental,
        (
            "UV Bake V2 should remain "
            "experimental during V2 development."
        ),
    )

    for method_name in (
        "execute",
        "availability",
        "draw_settings",
    ):
        _require(
            callable(
                getattr(
                    uv_bake,
                    method_name,
                    None,
                )
            ),
            (
                "UV Bake V2 missing "
                f"{method_name}()."
            ),
        )

    print(
        "Registry: OK"
    )

    for implementation_id in (
        actual_ids
    ):
        suffix = ""

        if (
            implementation_id
            == "projected-color-v1.2"
        ):
            suffix = (
                " [MATERIAL default]"
            )

        elif (
            implementation_id
            == "uv-bake-v2"
        ):
            suffix = (
                " [MATERIAL experimental]"
            )

        print(
            (
                f"  OK  "
                f"{implementation_id}"
                f"{suffix}"
            )
        )


# =========================================================
# Generic GEOMETRY -> MATERIAL compatibility
# =========================================================

def _validate_generic_geometry_material_compatibility(
    package_name: str,
    settings,
) -> None:
    """
    Critical architecture smoke test.

    Build a real Blender mesh but wrap it only in the generic
    GeometrySurfaceOutput contract.

    The fake implementation deliberately identifies itself as:

        sdf-reconstruction-v1

    and is NOT a NativeVisualHullOutput.

    Both current MATERIAL implementations must still report:

        READY

    This proves that MATERIAL no longer requires:

        NativeVisualHullOutput
        NativeVolume
        NativeMesh
    """

    _section(
        "generic GEOMETRY -> MATERIAL"
    )

    geometry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.geometry_contracts"
            )
        )
    )

    contracts_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_contracts"
            )
        )
    )

    registry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_registry"
            )
        )
    )

    native_geometry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations."
                "native_visual_hull"
            )
        )
    )

    GeometryProjectionSpace = (
        geometry_module
        .GeometryProjectionSpace
    )

    GeometrySurfaceOutput = (
        geometry_module
        .GeometrySurfaceOutput
    )

    PipelineContext = (
        contracts_module
        .PipelineContext
    )

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    NativeVisualHullOutput = (
        native_geometry_module
        .NativeVisualHullOutput
    )

    registry = (
        registry_module
        .PIPELINE_REGISTRY
    )

    mesh = None

    obj = None

    try:
        # -------------------------------------------------
        # Tiny real Blender surface.
        #
        # Availability validation checks:
        #
        #     MESH object
        #     vertices
        #     polygons
        #     loops
        #
        # It does NOT execute projection or UV bake here.
        # -------------------------------------------------

        mesh = (
            bpy.data.meshes.new(
                (
                    "Meshvenn "
                    "Generic Geometry "
                    "Smoke Mesh"
                )
            )
        )

        mesh.from_pydata(
            [
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    1.0,
                    0.0,
                    0.0,
                ),
                (
                    0.0,
                    1.0,
                    0.0,
                ),
            ],
            [],
            [
                (
                    0,
                    1,
                    2,
                )
            ],
        )

        mesh.update()

        obj = (
            bpy.data.objects.new(
                (
                    "Meshvenn "
                    "Generic Geometry "
                    "Smoke Object"
                ),
                mesh,
            )
        )

        scene = (
            bpy.context.scene
        )

        _require(
            scene is not None,
            (
                "No Blender scene available "
                "for generic GEOMETRY smoke."
            ),
        )

        scene.collection.objects.link(
            obj
        )

        # -------------------------------------------------
        # Fake INPUT capability.
        #
        # Availability only requires a non-empty iterable.
        # The actual ProjectedMaterialView contents are
        # validated when MATERIAL executes.
        # -------------------------------------------------

        fake_source = (
            SimpleNamespace(
                material_views=(
                    object(),
                    object(),
                ),
            )
        )

        projection_space = (
            GeometryProjectionSpace(
                width=16,
                depth=16,
                height=16,
                voxel_size=1.0,
                center_xy=True,
            )
        )

        geometry_output = (
            GeometrySurfaceOutput(
                blender_object=obj,

                source=(
                    fake_source
                ),

                projection_space=(
                    projection_space
                ),

                implementation_id=(
                    FAKE_GEOMETRY_IMPLEMENTATION_ID
                ),

                metrics={
                    "vertex_count": (
                        len(
                            mesh.vertices
                        )
                    ),

                    "polygon_count": (
                        len(
                            mesh.polygons
                        )
                    ),
                },

                metadata={
                    "smoke_test": True,

                    "algorithm": (
                        "fake-sdf"
                    ),
                },
            )
        )

        # -------------------------------------------------
        # Critical proof:
        #
        # the fake SDF contract is generic and must NOT be
        # a NativeVisualHullOutput.
        # -------------------------------------------------

        _require(
            isinstance(
                geometry_output,
                GeometrySurfaceOutput,
            ),
            (
                "Fake SDF geometry does not "
                "implement GeometrySurfaceOutput."
            ),
        )

        _require(
            not isinstance(
                geometry_output,
                NativeVisualHullOutput,
            ),
            (
                "Generic MATERIAL smoke accidentally "
                "used NativeVisualHullOutput."
            ),
        )

        _require(
            not hasattr(
                geometry_output,
                "volume",
            ),
            (
                "Generic fake SDF geometry "
                "unexpectedly exposes NativeVolume."
            ),
        )

        _require(
            not hasattr(
                geometry_output,
                "native_mesh",
            ),
            (
                "Generic fake SDF geometry "
                "unexpectedly exposes NativeMesh."
            ),
        )

        # -------------------------------------------------
        # Context
        # -------------------------------------------------

        context = (
            PipelineContext(
                scene=scene,
                settings=settings,
            )
        )

        context.set_output(
            PipelineStage.GEOMETRY,
            geometry_output,
        )

        resolved_geometry = (
            geometry_module
            .require_geometry_surface_output(
                context
            )
        )

        _require(
            resolved_geometry
            is geometry_output,
            (
                "Generic GEOMETRY accessor did "
                "not return the supplied output."
            ),
        )

        # -------------------------------------------------
        # Projected Color V1.2
        # -------------------------------------------------

        projected_color = (
            registry.require(
                "projected-color-v1.2",
                stage=(
                    PipelineStage.MATERIAL
                ),
            )
        )

        projected_availability = (
            projected_color
            .availability(
                context
            )
        )

        _require(
            projected_availability.ready,
            (
                "Projected Color V1.2 rejected "
                "generic non-Visual-Hull geometry.\n"
                f"State: "
                f"{projected_availability.state.value}\n"
                f"Reason: "
                f"{projected_availability.reason}\n"
                f"Details: "
                f"{dict(projected_availability.details)}"
            ),
        )

        # -------------------------------------------------
        # UV Bake V2
        # -------------------------------------------------

        uv_bake = (
            registry.require(
                "uv-bake-v2",
                stage=(
                    PipelineStage.MATERIAL
                ),
            )
        )

        uv_availability = (
            uv_bake
            .availability(
                context
            )
        )

        _require(
            uv_availability.ready,
            (
                "UV Bake V2 rejected generic "
                "non-Visual-Hull geometry.\n"
                f"State: "
                f"{uv_availability.state.value}\n"
                f"Reason: "
                f"{uv_availability.reason}\n"
                f"Details: "
                f"{dict(uv_availability.details)}"
            ),
        )

        # -------------------------------------------------
        # Availability diagnostics should expose the actual
        # GEOMETRY implementation, not assume visual hull.
        # -------------------------------------------------

        _require(
            (
                projected_availability
                .details
                .get(
                    "geometry_implementation"
                )
                == FAKE_GEOMETRY_IMPLEMENTATION_ID
            ),
            (
                "Projected Color availability "
                "did not preserve generic "
                "GEOMETRY implementation identity."
            ),
        )

        _require(
            (
                uv_availability
                .details
                .get(
                    "geometry_implementation"
                )
                == FAKE_GEOMETRY_IMPLEMENTATION_ID
            ),
            (
                "UV Bake availability "
                "did not preserve generic "
                "GEOMETRY implementation identity."
            ),
        )

        print(
            "Generic GEOMETRY compatibility: OK"
        )

        print(
            (
                "  geometry: "
                f"{FAKE_GEOMETRY_IMPLEMENTATION_ID}"
            )
        )

        print(
            (
                "  contract: "
                f"{projection_space.convention.value}"
            )
        )

        print(
            "  projected-color-v1.2: READY"
        )

        print(
            "  uv-bake-v2:             READY"
        )

    finally:
        # -------------------------------------------------
        # Smoke-test temporary Blender data must not leak
        # into later registration/unregistration checks.
        # -------------------------------------------------

        if obj is not None:
            try:
                bpy.data.objects.remove(
                    obj,
                    do_unlink=True,
                )

            except Exception:
                pass

        if (
            mesh is not None
            and mesh.users == 0
        ):
            try:
                bpy.data.meshes.remove(
                    mesh
                )

            except Exception:
                pass


# =========================================================
# Built-in catalog
# =========================================================

def _validate_builtin_catalog(
    package_name: str,
) -> None:
    _section(
        "built-in catalog"
    )

    module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations"
            )
        )
    )

    contracts_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_contracts"
            )
        )
    )

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    registered_ids = (
        module.registered_builtin_ids()
    )

    _require(
        registered_ids
        == EXPECTED_IMPLEMENTATIONS,
        (
            "Unexpected built-in "
            "implementation catalog."
        ),
    )

    _require(
        module
        .builtin_implementation_count()
        == 4,
        (
            "Built-in implementation "
            "count must be 4."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.INPUT
        )
        == "projection-images",
        (
            "Incorrect explicit INPUT "
            "built-in default."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.GEOMETRY
        )
        == "native-visual-hull",
        (
            "Incorrect explicit GEOMETRY "
            "built-in default."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.MATERIAL
        )
        == "projected-color-v1.2",
        (
            "UV Bake V2 accidentally "
            "replaced the MATERIAL "
            "built-in default."
        ),
    )

    print(
        "Built-in catalog: OK"
    )


# =========================================================
# Operators
# =========================================================

def _validate_operators_registered(
) -> None:
    _section(
        "operators"
    )

    for (
        rna_identifier,
        idname,
    ) in zip(
        EXPECTED_OPERATOR_RNA_IDS,
        EXPECTED_OPERATOR_IDNAMES,
        strict=True,
    ):
        operator_class = (
            _operator_rna_class(
                rna_identifier
            )
        )

        _require(
            operator_class
            is not None,
            (
                "Operator RNA class was "
                "not registered: "
                f"{rna_identifier}"
            ),
        )

        _require(
            operator_class.bl_idname
            == idname,
            (
                "Operator RNA id mismatch.\n"
                f"RNA:      {rna_identifier}\n"
                f"Expected: {idname}\n"
                "Actual:   "
                f"{operator_class.bl_idname}"
            ),
        )

        _require(
            _operator_available(
                idname
            ),
            (
                "bpy.ops operator "
                "is unavailable: "
                f"{idname}"
            ),
        )

        print(
            f"  OK  {idname}"
        )

    print(
        "Operators: OK"
    )


# =========================================================
# UI
# =========================================================

def _validate_ui_registered(
) -> None:
    _section(
        "ui"
    )

    panel = (
        _panel_rna_class(
            MAIN_PANEL_RNA_ID
        )
    )

    _require(
        panel is not None,
        (
            "Meshvenn main panel "
            "was not registered."
        ),
    )

    _require(
        panel.bl_idname
        == MAIN_PANEL_RNA_ID,
        (
            "Unexpected main panel "
            "bl_idname."
        ),
    )

    _require(
        panel.bl_space_type
        == "VIEW_3D",
        (
            "Meshvenn panel must "
            "use VIEW_3D."
        ),
    )

    _require(
        panel.bl_region_type
        == "UI",
        (
            "Meshvenn panel must "
            "use the UI region."
        ),
    )

    _require(
        panel.bl_category
        == "Meshvenn",
        (
            "Meshvenn panel category "
            "is incorrect."
        ),
    )

    _require(
        callable(
            getattr(
                panel,
                "draw",
                None,
            )
        ),
        (
            "Meshvenn panel does "
            "not expose draw()."
        ),
    )

    ui_list = (
        _ui_list_rna_class(
            PROJECTION_UI_LIST_RNA_ID
        )
    )

    _require(
        ui_list is not None,
        (
            "Projection UIList "
            "was not registered."
        ),
    )

    _require(
        callable(
            getattr(
                ui_list,
                "draw_item",
                None,
            )
        ),
        (
            "Projection UIList does "
            "not expose draw_item()."
        ),
    )

    print(
        f"  OK  {MAIN_PANEL_RNA_ID}"
    )

    print(
        f"  OK  {PROJECTION_UI_LIST_RNA_ID}"
    )

    print(
        "UI registration: OK"
    )


# =========================================================
# Unregistration
# =========================================================

def _validate_unregistered_state(
    package_name: str,
) -> None:
    _section(
        "unregister"
    )

    _require(
        not hasattr(
            bpy.types.Scene,
            "bpt_settings",
        ),
        (
            "Scene.bpt_settings still "
            "exists after unregister()."
        ),
    )

    for rna_identifier in (
        EXPECTED_OPERATOR_RNA_IDS
    ):
        _require(
            (
                _operator_rna_class(
                    rna_identifier
                )
                is None
            ),
            (
                "Operator remains registered "
                "after unregister(): "
                f"{rna_identifier}"
            ),
        )

    _require(
        (
            _panel_rna_class(
                MAIN_PANEL_RNA_ID
            )
            is None
        ),
        (
            "Main Meshvenn panel remains "
            "registered after unregister()."
        ),
    )

    _require(
        (
            _ui_list_rna_class(
                PROJECTION_UI_LIST_RNA_ID
            )
            is None
        ),
        (
            "Projection UIList remains "
            "registered after unregister()."
        ),
    )

    registry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_registry"
            )
        )
    )

    registry = (
        registry_module
        .PIPELINE_REGISTRY
    )

    _require(
        len(
            registry
        )
        == 0,
        (
            "Built-in implementations remain "
            "registered after unregister()."
        ),
    )

    implementations_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations"
            )
        )
    )

    _require(
        implementations_module
        .registered_builtin_ids()
        == (),
        (
            "Built-in implementation tracking "
            "was not cleared."
        ),
    )

    print(
        "Scene cleanup: OK"
    )

    print(
        "Operator cleanup: OK"
    )

    print(
        "UI cleanup: OK"
    )

    print(
        "Registry cleanup: OK"
    )


# =========================================================
# Main
# =========================================================

def main() -> None:
    arguments = (
        _parse_arguments()
    )

    package_root = Path(
        arguments.package_root
    )

    module = None

    package_name = None

    registered = False

    try:
        # -------------------------------------------------
        # Validate extracted ZIP, not repository source.
        # -------------------------------------------------

        _validate_package_tree(
            package_root
        )

        (
            module,
            package_name,
        ) = (
            _load_extension(
                package_root
            )
        )

        # -------------------------------------------------
        # Pure packaged core.
        # -------------------------------------------------

        _validate_geometry_contract_core(
            package_name
        )

        _validate_uv_bake_core(
            package_name
        )

        # -------------------------------------------------
        # Register extension.
        # -------------------------------------------------

        _section(
            "register extension"
        )

        module.register()

        registered = True

        print(
            "register(): OK"
        )

        # -------------------------------------------------
        # Blender state.
        # -------------------------------------------------

        settings = (
            _validate_scene_properties(
                package_name
            )
        )

        _validate_projection_defaults(
            settings
        )

        _validate_pipeline_defaults(
            settings
        )

        _validate_uv_bake_properties(
            settings
        )

        _validate_uv_bake_default_alignment(
            package_name,
            settings,
        )

        _validate_registry(
            package_name
        )

        # -------------------------------------------------
        # Critical architecture regression test.
        #
        # MATERIAL must accept generic GEOMETRY, not only
        # NativeVisualHullOutput.
        # -------------------------------------------------

        _validate_generic_geometry_material_compatibility(
            package_name,
            settings,
        )

        _validate_builtin_catalog(
            package_name
        )

        _validate_operators_registered()

        _validate_ui_registered()

        # -------------------------------------------------
        # Unregister.
        # -------------------------------------------------

        module.unregister()

        registered = False

        _validate_unregistered_state(
            package_name
        )

    except Exception:
        print()

        print(
            "=" * 72
        )

        print(
            "MESHVENN BLENDER SMOKE: FAILED"
        )

        print(
            "=" * 72
        )

        print()

        traceback.print_exc()

        if (
            registered
            and module is not None
        ):
            try:
                module.unregister()

            except Exception:
                print()

                print(
                    "Cleanup after failure failed:"
                )

                traceback.print_exc()

        raise SystemExit(
            1
        )

    print()

    print(
        "=" * 72
    )

    print(
        "MESHVENN BLENDER SMOKE: SUCCESS"
    )

    print(
        "=" * 72
    )


if __name__ == "__main__":
    main()