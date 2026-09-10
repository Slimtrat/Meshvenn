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

    # Core pipeline
    "core/__init__.py",
    "core/pipeline_contracts.py",
    "core/pipeline_registry.py",
    "core/pipeline_runner.py",
    "core/geometry_contracts.py",

    # Input / projection
    "core/image_mask.py",
    "core/projection_math.py",

    # Native geometry
    "core/native_loader.py",
    "core/native_bridge.py",
    "core/native_mesh_builder.py",
    "core/native_scan.py",

    # SDF geometry
    "core/sdf.py",
    "core/sdf_surface.py",

    # Material
    "core/projected_material.py",
    "core/material_visibility.py",
    "core/material_blend.py",
    "core/uv_bake.py",

    # Implementations
    "implementations/__init__.py",
    "implementations/projection_images.py",
    "implementations/native_visual_hull.py",
    "implementations/sdf_reconstruction.py",
    "implementations/projected_color.py",
    "implementations/uv_bake.py",

    # Native binaries
    "native/bin/libbpt_core.so",
    "native/bin/bpt_core.dll",
)


EXPECTED_IMPLEMENTATIONS = (
    "projection-images",
    "native-visual-hull",
    "sdf-reconstruction-v1",
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
# Generic GEOMETRY
# =========================================================

EXPECTED_GEOMETRY_CONTRACT = (
    "surface-envelope-v1"
)

FAKE_GEOMETRY_IMPLEMENTATION_ID = (
    "fake-sdf-surface"
)


# =========================================================
# SDF expected defaults
# =========================================================

EXPECTED_SDF_RESOLUTION = 96

EXPECTED_SDF_MINIMUM_RESOLUTION = 16

EXPECTED_SDF_REFERENCE_MAX_RESOLUTION = 160

EXPECTED_SDF_SYMMETRY_X = False

EXPECTED_SDF_SMOOTHNESS = 0.0

EXPECTED_SDF_SURFACE_OFFSET = 0.0

EXPECTED_SDF_ISO_LEVEL = 0.0

EXPECTED_SDF_GRADIENT_STEP_SCALE = 0.5


# =========================================================
# UV Bake expected defaults
# =========================================================

EXPECTED_UV_BAKE_TEXTURE_SIZE = "512"

EXPECTED_UV_BAKE_TEXTURE_SIZE_INT = int(
    EXPECTED_UV_BAKE_TEXTURE_SIZE
)

EXPECTED_UV_BAKE_PADDING_PIXELS = 8

EXPECTED_UV_BAKE_SAMPLES_PER_AXIS = "1"

EXPECTED_UV_BAKE_UV_LAYER_NAME = (
    "MeshvennUV"
)

EXPECTED_UV_BAKE_ISLAND_MARGIN = 0.02

EXPECTED_UV_BAKE_ANGLE_LIMIT_DEGREES = 66.0

EXPECTED_UV_BAKE_REUSE_EXISTING_UV = False

EXPECTED_SMART_PROJECT_MARGIN_PIXELS = 0.5


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

    index = sys.argv.index(
        "--"
    )

    return sys.argv[
        index + 1:
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
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Helpers
# =========================================================

def _section(
    title: str,
) -> None:
    print()
    print("=" * 72)
    print(
        f"Meshvenn smoke | {title}"
    )
    print("=" * 72)


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
        float(actual),
        float(expected),
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
# RNA helpers
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

    return getattr(
        getattr(
            bpy.ops,
            namespace_name,
        ),
        operator_name,
    )


def _operator_available(
    idname: str,
) -> bool:
    try:
        _operator_callable(
            idname
        ).get_rna_type()

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

    missing = [
        relative_path
        for relative_path
        in REQUIRED_PACKAGE_FILES
        if not (
            package_root
            / relative_path
        ).is_file()
    ]

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

    parent_string = str(
        package_parent
    )

    if (
        parent_string
        not in sys.path
    ):
        sys.path.insert(
            0,
            parent_string,
        )

    module = importlib.import_module(
        package_name
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
        f"Package root: {package_root}"
    )

    print(
        f"Module name: {package_name}"
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


# =========================================================
# Scene properties
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
            "No active Blender scene."
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
            "Scene does not expose "
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
            f"Expected: {EXPECTED_PROJECTION_NAMES}\n"
            f"Actual:   {actual_names}"
        ),
    )

    print(
        "Default projections: OK"
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
        pipeline.initialized,
        (
            "Pipeline defaults were "
            "not initialized."
        ),
    )

    expected = (
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
        wanted,
        stage_name,
    ) in expected:
        _require(
            actual == wanted,
            (
                f"Unexpected {stage_name} "
                "default implementation.\n"
                f"Expected: {wanted}\n"
                f"Actual:   {actual}"
            ),
        )

    _require(
        pipeline.input_stage.enabled,
        "INPUT must be enabled.",
    )

    _require(
        pipeline.geometry_stage.enabled,
        "GEOMETRY must be enabled.",
    )

    _require(
        pipeline.material_stage.enabled,
        "MATERIAL must be enabled.",
    )

    _require(
        not pipeline.rig_stage.enabled,
        "RIG must be disabled.",
    )

    _require(
        not pipeline.export_stage.enabled,
        "EXPORT must be disabled.",
    )

    print(
        "Pipeline defaults: OK"
    )

    print(
        "  GEOMETRY native-visual-hull [default]"
    )

    print(
        "           sdf-reconstruction-v1 [available]"
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


# =========================================================
# SDF defaults alignment
# =========================================================

def _validate_sdf_default_alignment(
    package_name: str,
    settings,
) -> None:
    _section(
        "SDF default alignment"
    )

    core_module = (
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

    implementation_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations."
                "sdf_reconstruction"
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

    _require(
        properties_module
        .DEFAULT_SDF_RESOLUTION
        == EXPECTED_SDF_RESOLUTION,
        (
            "properties.py SDF "
            "resolution is out of sync."
        ),
    )

    _require(
        implementation_module
        .DEFAULT_RESOLUTION
        == EXPECTED_SDF_RESOLUTION,
        (
            "SDF implementation "
            "resolution is out of sync."
        ),
    )

    _require(
        properties_module
        .MINIMUM_SDF_RESOLUTION
        == implementation_module
        .MINIMUM_RESOLUTION
        == EXPECTED_SDF_MINIMUM_RESOLUTION,
        (
            "SDF minimum resolution "
            "is out of sync."
        ),
    )

    _require(
        properties_module
        .MAXIMUM_SDF_REFERENCE_RESOLUTION
        == EXPECTED_SDF_REFERENCE_MAX_RESOLUTION,
        (
            "SDF reference UI max "
            "is out of sync."
        ),
    )

    _require(
        EXPECTED_SDF_REFERENCE_MAX_RESOLUTION
        <= implementation_module
        .MAXIMUM_RESOLUTION,
        (
            "SDF property limit exceeds "
            "implementation limit."
        ),
    )

    _require(
        (
            EXPECTED_SDF_REFERENCE_MAX_RESOLUTION
            ** 3
        )
        <= core_module
        .DEFAULT_REFERENCE_MAX_VOXELS,
        (
            "SDF UI allows more samples "
            "than the Python reference "
            "backend accepts."
        ),
    )

    config = (
        implementation_module
        .SDFReconstructionConfig()
    )

    config.validate()

    _require(
        config.resolution
        == EXPECTED_SDF_RESOLUTION,
        (
            "SDFReconstructionConfig "
            "resolution is out of sync."
        ),
    )

    _require(
        config.symmetry_x
        == EXPECTED_SDF_SYMMETRY_X,
        (
            "SDFReconstructionConfig "
            "symmetry is out of sync."
        ),
    )

    _require_close(
        config.smoothness,
        core_module.DEFAULT_SMOOTHNESS,
        name=(
            "implementation/core "
            "SDF smoothness"
        ),
    )

    _require_close(
        config.surface_offset,
        core_module.DEFAULT_SURFACE_OFFSET,
        name=(
            "implementation/core "
            "surface offset"
        ),
    )

    _require_close(
        config.iso_level,
        core_module.DEFAULT_ISO_LEVEL,
        name=(
            "implementation/core "
            "iso level"
        ),
    )

    _require_close(
        config.gradient_step_scale,
        surface_module
        .DEFAULT_GRADIENT_STEP_SCALE,
        name=(
            "implementation/core "
            "gradient step"
        ),
    )

    _require(
        settings.sdf_resolution
        == config.resolution,
        (
            "Scene SDF resolution "
            "is out of sync."
        ),
    )

    print(
        "SDF defaults aligned: OK"
    )

    print(
        (
            "  core max samples: "
            f"{core_module.DEFAULT_REFERENCE_MAX_VOXELS:,}"
        )
    )

    print(
        (
            "  implementation: "
            f"{config.resolution}³"
        )
    )

    print(
        (
            "  scene RNA:      "
            f"{settings.sdf_resolution}³"
        )
    )


# =========================================================
# SDF pipeline selection
# =========================================================

def _validate_sdf_pipeline_selection(
    package_name: str,
    settings,
) -> None:
    _section(
        "SDF pipeline selection"
    )

    properties_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "properties"
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

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    previous = (
        properties_module
        .get_pipeline_implementation(
            settings,
            PipelineStage.GEOMETRY,
        )
    )

    try:
        properties_module
        .set_pipeline_implementation(
            settings,
            PipelineStage.GEOMETRY,
            "sdf-reconstruction-v1",
        )

        plan = (
            properties_module
            .build_pipeline_plan(
                settings
            )
        )

        selection = (
            plan.selection_for(
                PipelineStage.GEOMETRY
            )
        )

        _require(
            selection is not None,
            (
                "SDF GEOMETRY selection "
                "disappeared from PipelinePlan."
            ),
        )

        _require(
            selection.implementation_id
            == "sdf-reconstruction-v1",
            (
                "PipelinePlan did not preserve "
                "SDF implementation selection."
            ),
        )

        _require(
            selection.enabled,
            (
                "Selected SDF GEOMETRY "
                "stage is disabled."
            ),
        )

        # Selecting SDF in scene state MUST NOT mutate the
        # global built-in default.
        _require(
            registry_module
            .PIPELINE_REGISTRY
            .default_id(
                PipelineStage.GEOMETRY
            )
            == "native-visual-hull",
            (
                "Selecting SDF changed the "
                "GEOMETRY registry default."
            ),
        )

    finally:
        properties_module
        .set_pipeline_implementation(
            settings,
            PipelineStage.GEOMETRY,
            previous,
        )

    print(
        "SDF selection: OK"
    )

    print(
        "  selectable: sdf-reconstruction-v1"
    )

    print(
        "  global default unchanged: native-visual-hull"
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
            f"Expected: {EXPECTED_IMPLEMENTATIONS}\n"
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

    # -----------------------------------------------------
    # SDF
    # -----------------------------------------------------

    sdf = (
        registry.require(
            "sdf-reconstruction-v1",
            stage=(
                PipelineStage.GEOMETRY
            ),
        )
    )

    sdf_descriptor = (
        sdf.descriptor
    )

    _require(
        sdf_descriptor.identifier
        == "sdf-reconstruction-v1",
        (
            "Unexpected SDF "
            "implementation id."
        ),
    )

    _require(
        sdf_descriptor.stage
        == PipelineStage.GEOMETRY,
        (
            "SDF must belong "
            "to GEOMETRY."
        ),
    )

    _require(
        sdf_descriptor.label
        == "SDF Reconstruction V1",
        (
            "Unexpected SDF label."
        ),
    )

    _require(
        sdf_descriptor.experimental,
        (
            "SDF V1 should remain "
            "experimental."
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
                    sdf,
                    method_name,
                    None,
                )
            ),
            (
                "SDF implementation "
                f"missing {method_name}()."
            ),
        )

    # -----------------------------------------------------
    # UV Bake
    # -----------------------------------------------------

    uv_bake = (
        registry.require(
            "uv-bake-v2",
            stage=(
                PipelineStage.MATERIAL
            ),
        )
    )

    _require(
        uv_bake.descriptor.experimental,
        (
            "UV Bake V2 should remain "
            "experimental."
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
            == "native-visual-hull"
        ):
            suffix = (
                " [GEOMETRY default]"
            )

        elif (
            implementation_id
            == "sdf-reconstruction-v1"
        ):
            suffix = (
                " [GEOMETRY experimental]"
            )

        elif (
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
    Use a real Blender mesh wrapped only in
    GeometrySurfaceOutput.

    It deliberately exposes no:

        NativeVolume
        NativeMesh
        SDFBuildResult
        SDFSurfaceResult

    Both MATERIAL implementations must accept it.
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

    native_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations."
                "native_visual_hull"
            )
        )
    )

    sdf_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations."
                "sdf_reconstruction"
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

    mesh = None
    obj = None

    try:
        mesh = (
            bpy.data.meshes.new(
                "Meshvenn Generic Geometry Smoke Mesh"
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
                    "Meshvenn Generic "
                    "Geometry Smoke Object"
                ),
                mesh,
            )
        )

        scene = (
            bpy.context.scene
        )

        scene.collection.objects.link(
            obj
        )

        fake_source = (
            SimpleNamespace(
                material_views=(
                    object(),
                    object(),
                )
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
                source=fake_source,
                projection_space=(
                    projection_space
                ),
                implementation_id=(
                    FAKE_GEOMETRY_IMPLEMENTATION_ID
                ),
                metrics={
                    "vertex_count":
                        len(
                            mesh.vertices
                        ),

                    "polygon_count":
                        len(
                            mesh.polygons
                        ),
                },
            )
        )

        _require(
            not isinstance(
                geometry_output,
                native_module
                .NativeVisualHullOutput,
            ),
            (
                "Generic test accidentally "
                "uses NativeVisualHullOutput."
            ),
        )

        _require(
            not isinstance(
                geometry_output,
                sdf_module
                .SDFReconstructionOutput,
            ),
            (
                "Generic test accidentally "
                "uses SDFReconstructionOutput."
            ),
        )

        _require(
            not hasattr(
                geometry_output,
                "volume",
            ),
            (
                "Generic geometry exposes "
                "native volume."
            ),
        )

        _require(
            not hasattr(
                geometry_output,
                "sdf_result",
            ),
            (
                "Generic geometry exposes "
                "SDF internals."
            ),
        )

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

        projected = (
            registry_module
            .PIPELINE_REGISTRY
            .require(
                "projected-color-v1.2",
                stage=(
                    PipelineStage.MATERIAL
                ),
            )
        )

        projected_status = (
            projected.availability(
                context
            )
        )

        _require(
            projected_status.ready,
            (
                "Projected Color rejected "
                "generic geometry.\n"
                f"{projected_status.reason}"
            ),
        )

        uv_bake = (
            registry_module
            .PIPELINE_REGISTRY
            .require(
                "uv-bake-v2",
                stage=(
                    PipelineStage.MATERIAL
                ),
            )
        )

        uv_status = (
            uv_bake.availability(
                context
            )
        )

        _require(
            uv_status.ready,
            (
                "UV Bake rejected "
                "generic geometry.\n"
                f"{uv_status.reason}"
            ),
        )

        _require(
            projected_status
            .details
            .get(
                "geometry_implementation"
            )
            == FAKE_GEOMETRY_IMPLEMENTATION_ID,
            (
                "Projected Color lost "
                "generic geometry identity."
            ),
        )

        _require(
            uv_status
            .details
            .get(
                "geometry_implementation"
            )
            == FAKE_GEOMETRY_IMPLEMENTATION_ID,
            (
                "UV Bake lost "
                "generic geometry identity."
            ),
        )

        print(
            "Generic GEOMETRY compatibility: OK"
        )

        print(
            "  projected-color-v1.2: READY"
        )

        print(
            "  uv-bake-v2:             READY"
        )

    finally:
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

    _require(
        module.registered_builtin_ids()
        == EXPECTED_IMPLEMENTATIONS,
        (
            "Unexpected built-in "
            "implementation catalog."
        ),
    )

    _require(
        module
        .builtin_implementation_count()
        == 5,
        (
            "Built-in implementation "
            "count must be 5."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.INPUT
        )
        == "projection-images",
        (
            "Incorrect INPUT default."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.GEOMETRY
        )
        == "native-visual-hull",
        (
            "SDF accidentally replaced "
            "the GEOMETRY default."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.MATERIAL
        )
        == "projected-color-v1.2",
        (
            "UV Bake accidentally replaced "
            "the MATERIAL default."
        ),
    )

    print(
        "Built-in catalog: OK"
    )

    print(
        "  5 implementations"
    )

    print(
        "  GEOMETRY default preserved"
    )


# =========================================================
# Operators
# =========================================================

def _validate_operators_registered() -> None:
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
                "Operator RNA class "
                f"missing: {rna_identifier}"
            ),
        )

        _require(
            operator_class.bl_idname
            == idname,
            (
                "Operator id mismatch.\n"
                f"Expected: {idname}\n"
                f"Actual: "
                f"{operator_class.bl_idname}"
            ),
        )

        _require(
            _operator_available(
                idname
            ),
            (
                "bpy.ops operator "
                f"unavailable: {idname}"
            ),
        )

    print(
        "Operators: OK"
    )


# =========================================================
# UI
# =========================================================

def _validate_ui_registered() -> None:
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
            "Meshvenn panel "
            "not registered."
        ),
    )

    _require(
        panel.bl_idname
        == MAIN_PANEL_RNA_ID,
        (
            "Unexpected panel bl_idname."
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
            "use UI region."
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

    ui_list = (
        _ui_list_rna_class(
            PROJECTION_UI_LIST_RNA_ID
        )
    )

    _require(
        ui_list is not None,
        (
            "Projection UIList "
            "not registered."
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
            "Projection UIList "
            "missing draw_item()."
        ),
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

    for identifier in (
        EXPECTED_OPERATOR_RNA_IDS
    ):
        _require(
            _operator_rna_class(
                identifier
            )
            is None,
            (
                "Operator still registered: "
                f"{identifier}"
            ),
        )

    _require(
        _panel_rna_class(
            MAIN_PANEL_RNA_ID
        )
        is None,
        (
            "Main panel still registered."
        ),
    )

    _require(
        _ui_list_rna_class(
            PROJECTION_UI_LIST_RNA_ID
        )
        is None,
        (
            "Projection UIList "
            "still registered."
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

    _require(
        len(
            registry_module
            .PIPELINE_REGISTRY
        )
        == 0,
        (
            "Built-ins remain in registry "
            "after unregister()."
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
            "Built-in tracking "
            "was not cleared."
        ),
    )

    print(
        "Unregister: OK"
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
        # Actual distributable package
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
        # Pure packaged core
        # -------------------------------------------------

        _validate_geometry_contract_core(
            package_name
        )

        _validate_sdf_core(
            package_name
        )

        _validate_uv_bake_core(
            package_name
        )

        # -------------------------------------------------
        # Register extension
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
        # Blender state
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

        # SDF
        _validate_sdf_properties(
            settings
        )

        _validate_sdf_default_alignment(
            package_name,
            settings,
        )

        _validate_registry(
            package_name
        )

        _validate_sdf_pipeline_selection(
            package_name,
            settings,
        )

        # UV Bake
        _validate_uv_bake_properties(
            settings
        )

        _validate_uv_bake_default_alignment(
            package_name,
            settings,
        )

        # Generic architecture guarantee
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
        # Unregister
        # -------------------------------------------------

        module.unregister()

        registered = False

        _validate_unregistered_state(
            package_name
        )

    except Exception:
        print()
        print("=" * 72)
        print(
            "MESHVENN BLENDER SMOKE: FAILED"
        )
        print("=" * 72)
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
    print("=" * 72)
    print(
        "MESHVENN BLENDER SMOKE: SUCCESS"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()