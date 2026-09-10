from __future__ import annotations

import argparse
import importlib
import sys
import traceback

from pathlib import Path
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

    "core/__init__.py",
    "core/pipeline_contracts.py",
    "core/pipeline_registry.py",
    "core/pipeline_runner.py",
    "core/image_mask.py",
    "core/native_loader.py",
    "core/native_bridge.py",
    "core/native_mesh_builder.py",
    "core/projected_material.py",
    "core/material_visibility.py",
    "core/material_blend.py",
    "core/projection_math.py",

    "implementations/__init__.py",
    "implementations/projection_images.py",
    "implementations/native_visual_hull.py",
    "implementations/projected_color.py",

    "native/bin/libbpt_core.so",
)


EXPECTED_IMPLEMENTATIONS = (
    "projection-images",
    "native-visual-hull",
    "projected-color-v1.2",
)


EXPECTED_PROJECTION_NAMES = (
    "Front",
    "Right",
    "Back",
    "Top",
)


# ---------------------------------------------------------
# Blender RNA identifiers
#
# Operator Python class:
#
#     BPT_OT_RunPipeline
#
# with:
#
#     bl_idname = "bpt.run_pipeline"
#
# is registered by Blender as:
#
#     BPT_OT_run_pipeline
#
# It must therefore not be looked up using the original
# Python class name.
# ---------------------------------------------------------

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
            "Smoke-test the packaged Meshvenn "
            "Blender extension."
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
    """
    Resolve e.g.:

        bpt.run_pipeline

    to:

        bpy.ops.bpt.run_pipeline
    """

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
    """
    Blender bpy.ops uses dynamic attribute access, so plain
    hasattr() is not a sufficiently strong registration
    test.

    get_rna_type() forces Blender to resolve the registered
    operator definition.
    """

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

    # Blender normally initializes defaults through its
    # registration timer. A headless smoke test must not
    # depend on timer/event-loop scheduling.
    properties_module.ensure_scene_defaults(
        scene
    )

    print(
        "Scene.bpt_settings: OK"
    )

    return settings


# =========================================================
# Default projections
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

    for name in actual_names:
        print(
            f"  OK  {name}"
        )


# =========================================================
# Persistent pipeline configuration
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

    _require(
        (
            pipeline
            .input_stage
            .implementation_id
        )
        == "projection-images",
        (
            "Unexpected INPUT "
            "implementation."
        ),
    )

    _require(
        (
            pipeline
            .geometry_stage
            .implementation_id
        )
        == "native-visual-hull",
        (
            "Unexpected GEOMETRY "
            "implementation."
        ),
    )

    _require(
        (
            pipeline
            .material_stage
            .implementation_id
        )
        == "projected-color-v1.2",
        (
            "Unexpected MATERIAL "
            "implementation."
        ),
    )

    _require(
        bool(
            pipeline
            .input_stage
            .enabled
        ),
        (
            "INPUT must be enabled "
            "by default."
        ),
    )

    _require(
        bool(
            pipeline
            .geometry_stage
            .enabled
        ),
        (
            "GEOMETRY must be enabled "
            "by default."
        ),
    )

    _require(
        bool(
            pipeline
            .material_stage
            .enabled
        ),
        (
            "MATERIAL must be enabled "
            "by default."
        ),
    )

    _require(
        not bool(
            pipeline
            .rig_stage
            .enabled
        ),
        (
            "RIG must be disabled "
            "by default."
        ),
    )

    _require(
        not bool(
            pipeline
            .export_stage
            .enabled
        ),
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
        "  RIG      disabled"
    )

    print(
        "  EXPORT   disabled"
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

    print(
        "Registry: OK"
    )

    for implementation_id in (
        actual_ids
    ):
        print(
            f"  OK  {implementation_id}"
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
                "Operator RNA class was not "
                "registered: "
                f"{rna_identifier}"
            ),
        )

        _require(
            (
                operator_class
                .bl_idname
            )
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
                "bpy.ops operator is unavailable: "
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
            "Meshvenn main panel "
            "was not registered."
        ),
    )

    _require(
        (
            panel.bl_idname
        )
        == MAIN_PANEL_RNA_ID,
        (
            "Unexpected main panel "
            "bl_idname."
        ),
    )

    _require(
        (
            panel.bl_space_type
        )
        == "VIEW_3D",
        (
            "Meshvenn panel must use "
            "VIEW_3D."
        ),
    )

    _require(
        (
            panel.bl_region_type
        )
        == "UI",
        (
            "Meshvenn panel must use "
            "the UI region."
        ),
    )

    _require(
        (
            panel.bl_category
        )
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
            "Meshvenn panel does not "
            "expose draw()."
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
            "Projection UIList was "
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
            "Projection UIList does not "
            "expose draw_item()."
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
        # Test exactly what was extracted from the release
        # ZIP, not the source checkout.
        # -------------------------------------------------

        _validate_package_tree(
            package_root
        )

        (
            module,
            package_name,
        ) = _load_extension(
            package_root
        )

        # -------------------------------------------------
        # Register
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
        # Validate registered extension
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

        _validate_registry(
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

        # -------------------------------------------------
        # Best-effort cleanup.
        #
        # A failed smoke must not hide the original failure
        # because unregister() itself throws.
        # -------------------------------------------------

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