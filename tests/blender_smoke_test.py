from __future__ import annotations

import argparse
import importlib
import sys
import traceback

from pathlib import Path

import bpy


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

DEFAULT_PACKAGE_ROOT = (
    Path("dist")
    / "blender_projection_tool"
)


REQUIRED_PACKAGE_FILES = (
    "__init__.py",
    "properties.py",
    "operators.py",
    "ui.py",

    "core/__init__.py",
    "core/pipeline_contracts.py",
    "core/pipeline_registry.py",
    "core/pipeline_runner.py",

    "implementations/__init__.py",
    "implementations/projection_images.py",
    "implementations/native_visual_hull.py",
    "implementations/projected_color.py",
)


EXPECTED_IMPLEMENTATIONS = (
    "projection-images",
    "native-visual-hull",
    "projected-color-v1.2",
)


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def _script_arguments() -> list[str]:
    """
    Blender arguments after `--` belong to this script.

    Example:

        blender \
            --background \
            --factory-startup \
            --python tests/blender_smoke_test.py \
            -- \
            --package-root dist/blender_projection_tool
    """

    if "--" not in sys.argv:
        return []

    separator = (
        sys.argv.index(
            "--"
        )
    )

    return sys.argv[
        separator + 1:
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
            "Path to the unpacked extension "
            "package directory."
        ),
    )

    return parser.parse_args(
        _script_arguments()
    )


# ---------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------

def _require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def _section(
    name: str,
) -> None:
    print()

    print(
        "=" * 72
    )

    print(
        f"Meshvenn smoke | {name}"
    )

    print(
        "=" * 72
    )


# ---------------------------------------------------------
# Package validation
# ---------------------------------------------------------

def _validate_package_tree(
    package_root: Path,
) -> None:
    _section(
        "package tree"
    )

    _require(
        package_root.is_dir(),
        (
            "Packaged extension directory "
            f"does not exist: {package_root}"
        ),
    )

    missing_files: list[str] = []

    for relative_path in (
        REQUIRED_PACKAGE_FILES
    ):
        path = (
            package_root
            / relative_path
        )

        if not path.is_file():
            missing_files.append(
                relative_path
            )

    if missing_files:
        formatted = "\n".join(
            f"  - {path}"
            for path
            in missing_files
        )

        raise AssertionError(
            (
                "Packaged extension is incomplete.\n"
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


# ---------------------------------------------------------
# Module loading
# ---------------------------------------------------------

def _purge_package_modules(
    module_name: str,
) -> None:
    """
    Ensure the smoke test imports from the packaged directory
    rather than reusing a module accidentally loaded from
    another checkout.
    """

    prefix = (
        module_name
        + "."
    )

    loaded_names = [
        name
        for name
        in tuple(
            sys.modules
        )
        if (
            name == module_name
            or name.startswith(
                prefix
            )
        )
    ]

    for name in sorted(
        loaded_names,
        key=len,
        reverse=True,
    ):
        sys.modules.pop(
            name,
            None,
        )


def _load_extension(
    package_root: Path,
):
    _section(
        "import extension"
    )

    package_root = (
        package_root
        .resolve()
    )

    package_parent = (
        package_root.parent
    )

    module_name = (
        package_root.name
    )

    _purge_package_modules(
        module_name
    )

    sys.path.insert(
        0,
        str(
            package_parent
        ),
    )

    print(
        f"Package root: {package_root}"
    )

    print(
        f"Module name: {module_name}"
    )

    module = (
        importlib.import_module(
            module_name
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
        module_name,
    )


# ---------------------------------------------------------
# Registration validation
# ---------------------------------------------------------

def _validate_registration(
    module,
    module_name: str,
) -> None:
    _section(
        "register extension"
    )

    module.register()

    print(
        "register(): OK"
    )

    # -----------------------------------------------------
    # Scene property
    # -----------------------------------------------------

    _require(
        hasattr(
            bpy.types.Scene,
            "bpt_settings",
        ),
        (
            "Scene.bpt_settings was not "
            "registered."
        ),
    )

    scene = (
        bpy.context.scene
    )

    _require(
        scene is not None,
        "No Blender scene available.",
    )

    settings = getattr(
        scene,
        "bpt_settings",
        None,
    )

    _require(
        settings is not None,
        (
            "Current scene has no "
            "bpt_settings instance."
        ),
    )

    print(
        "Scene.bpt_settings: OK"
    )

    # -----------------------------------------------------
    # Force defaults synchronously.
    #
    # properties.register() normally schedules this through
    # a Blender timer. A background CI smoke should not rely
    # on UI/event-loop timing.
    # -----------------------------------------------------

    properties_module = (
        importlib.import_module(
            (
                f"{module_name}."
                "properties"
            )
        )
    )

    properties_module.ensure_scene_defaults(
        scene
    )

    _require(
        bool(
            settings
            .pipeline
            .initialized
        ),
        (
            "Pipeline defaults were not "
            "initialized."
        ),
    )

    print(
        "Pipeline defaults: OK"
    )

    # -----------------------------------------------------
    # Default projections
    # -----------------------------------------------------

    _require(
        len(
            settings.projections
        )
        == 4,
        (
            "Expected 4 default projection "
            "slots, received "
            f"{len(settings.projections)}."
        ),
    )

    projection_names = tuple(
        projection.name
        for projection
        in settings.projections
    )

    _require(
        projection_names
        == (
            "Front",
            "Right",
            "Back",
            "Top",
        ),
        (
            "Unexpected default projections: "
            f"{projection_names}"
        ),
    )

    print(
        "Default projection slots: OK"
    )

    # -----------------------------------------------------
    # Persistent pipeline selections
    # -----------------------------------------------------

    _require(
        (
            settings
            .pipeline
            .input_stage
            .implementation_id
        )
        == "projection-images",
        (
            "Unexpected INPUT default "
            "implementation."
        ),
    )

    _require(
        (
            settings
            .pipeline
            .geometry_stage
            .implementation_id
        )
        == "native-visual-hull",
        (
            "Unexpected GEOMETRY default "
            "implementation."
        ),
    )

    _require(
        (
            settings
            .pipeline
            .material_stage
            .implementation_id
        )
        == "projected-color-v1.2",
        (
            "Unexpected MATERIAL default "
            "implementation."
        ),
    )

    _require(
        not (
            settings
            .pipeline
            .rig_stage
            .enabled
        ),
        (
            "RIG must be disabled by default "
            "until an implementation exists."
        ),
    )

    _require(
        not (
            settings
            .pipeline
            .export_stage
            .enabled
        ),
        (
            "EXPORT must be disabled by default "
            "until an implementation exists."
        ),
    )

    print(
        "Persistent stage configuration: OK"
    )

    # -----------------------------------------------------
    # Registry
    # -----------------------------------------------------

    registry_module = (
        importlib.import_module(
            (
                f"{module_name}."
                "core.pipeline_registry"
            )
        )
    )

    contracts_module = (
        importlib.import_module(
            (
                f"{module_name}."
                "core.pipeline_contracts"
            )
        )
    )

    registry = (
        registry_module
        .PIPELINE_REGISTRY
    )

    registered_ids = (
        registry
        .implementation_ids()
    )

    _require(
        registered_ids
        == EXPECTED_IMPLEMENTATIONS,
        (
            "Unexpected pipeline registry.\n"
            f"Expected: {EXPECTED_IMPLEMENTATIONS}\n"
            f"Actual:   {registered_ids}"
        ),
    )

    print(
        "Registry implementations: OK"
    )

    for implementation_id in (
        registered_ids
    ):
        print(
            f"  OK  {implementation_id}"
        )

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    _require(
        registry.default_id(
            PipelineStage.INPUT
        )
        == "projection-images",
        (
            "Unexpected INPUT registry "
            "default."
        ),
    )

    _require(
        registry.default_id(
            PipelineStage.GEOMETRY
        )
        == "native-visual-hull",
        (
            "Unexpected GEOMETRY registry "
            "default."
        ),
    )

    _require(
        registry.default_id(
            PipelineStage.MATERIAL
        )
        == "projected-color-v1.2",
        (
            "Unexpected MATERIAL registry "
            "default."
        ),
    )

    _require(
        registry.default_id(
            PipelineStage.RIG
        )
        is None,
        (
            "RIG registry should have no "
            "default implementation yet."
        ),
    )

    _require(
        registry.default_id(
            PipelineStage.EXPORT
        )
        is None,
        (
            "EXPORT registry should have no "
            "default implementation yet."
        ),
    )

    print(
        "Registry defaults: OK"
    )

    # -----------------------------------------------------
    # Operators
    # -----------------------------------------------------

    required_operator_types = (
        "BPT_OT_LoadProjectionImage",
        "BPT_OT_ImportTurntableImages",
        "BPT_OT_AddProjection",
        "BPT_OT_RemoveProjection",
        "BPT_OT_AddTurntablePreset",
        "BPT_OT_AddFrontSidePreset",
        "BPT_OT_SetPipelineImplementation",
        "BPT_OT_ResetPipelineSettings",
        "BPT_OT_RunPipeline",
        "BPT_OT_RunPipelineStage",
        "BPT_OT_GenerateCharacter",
    )

    for type_name in (
        required_operator_types
    ):
        _require(
            hasattr(
                bpy.types,
                type_name,
            ),
            (
                "Blender operator type "
                f"{type_name} is not registered."
            ),
        )

    print(
        "Operators: OK"
    )

    # -----------------------------------------------------
    # UI registration
    #
    # A background Blender process does not expose a normal
    # interactive VIEW_3D draw cycle, so the smoke verifies
    # RNA registration rather than attempting to fake a
    # UILayout.
    #
    # This still catches:
    #
    #   - import errors;
    #   - class registration errors;
    #   - duplicate ids;
    #   - broken Panel/UIList definitions.
    # -----------------------------------------------------

    required_ui_types = (
        "BPT_UL_ProjectionViews",
        "BPT_PT_MainPanel",
    )

    for type_name in (
        required_ui_types
    ):
        _require(
            hasattr(
                bpy.types,
                type_name,
            ),
            (
                "Blender UI type "
                f"{type_name} is not registered."
            ),
        )

    panel_type = getattr(
        bpy.types,
        "BPT_PT_MainPanel",
    )

    _require(
        panel_type.bl_space_type
        == "VIEW_3D",
        (
            "Meshvenn panel is registered "
            "in an unexpected Blender space."
        ),
    )

    _require(
        panel_type.bl_region_type
        == "UI",
        (
            "Meshvenn panel is registered "
            "in an unexpected Blender region."
        ),
    )

    _require(
        panel_type.bl_category
        == "Meshvenn",
        (
            "Meshvenn panel category is "
            "unexpected."
        ),
    )

    _require(
        callable(
            getattr(
                panel_type,
                "draw",
                None,
            )
        ),
        (
            "Meshvenn main panel has no "
            "draw() method."
        ),
    )

    print(
        "UI registration: OK"
    )


# ---------------------------------------------------------
# Unregister validation
# ---------------------------------------------------------

def _validate_unregistration(
    module,
    module_name: str,
) -> None:
    _section(
        "unregister extension"
    )

    module.unregister()

    print(
        "unregister(): OK"
    )

    _require(
        not hasattr(
            bpy.types.Scene,
            "bpt_settings",
        ),
        (
            "Scene.bpt_settings still exists "
            "after unregister()."
        ),
    )

    for type_name in (
        "BPT_PT_MainPanel",
        "BPT_UL_ProjectionViews",
        "BPT_OT_RunPipeline",
        "BPT_OT_RunPipelineStage",
    ):
        _require(
            not hasattr(
                bpy.types,
                type_name,
            ),
            (
                f"{type_name} still registered "
                "after unregister()."
            ),
        )

    registry_module = (
        importlib.import_module(
            (
                f"{module_name}."
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
            "Built-in pipeline implementations "
            "remain registered after "
            "unregister()."
        ),
    )

    print(
        "Cleanup: OK"
    )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    arguments = (
        _parse_arguments()
    )

    package_root = Path(
        arguments.package_root
    )

    module = None

    module_name = None

    registered = False

    try:
        _validate_package_tree(
            package_root
        )

        (
            module,
            module_name,
        ) = _load_extension(
            package_root
        )

        # Registration is inside its own phase so cleanup can
        # still be attempted if a later assertion fails.
        module.register()

        registered = True

        # We called register() above so validation below must
        # not call it a second time.
        #
        # Temporarily expose a tiny adapter to keep the
        # registration tests grouped clearly.
        _validate_registered_state(
            module,
            module_name,
        )

        module.unregister()

        registered = False

        _validate_unregistered_state(
            module_name
        )

    except Exception:
        print()

        print(
            "MESHVENN BLENDER SMOKE: FAILED"
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
                    "Cleanup after failure also failed:"
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


# ---------------------------------------------------------
# Registered-state checks
# ---------------------------------------------------------

def _validate_registered_state(
    module,
    module_name: str,
) -> None:
    """
    Same validations as _validate_registration(), except the
    extension has already been registered by main() so we can
    guarantee cleanup state accurately.
    """

    _section(
        "registered extension"
    )

    _require(
        hasattr(
            bpy.types.Scene,
            "bpt_settings",
        ),
        (
            "Scene.bpt_settings was not "
            "registered."
        ),
    )

    scene = (
        bpy.context.scene
    )

    _require(
        scene is not None,
        "No Blender scene available.",
    )

    settings = (
        scene.bpt_settings
    )

    properties_module = (
        importlib.import_module(
            (
                f"{module_name}."
                "properties"
            )
        )
    )

    properties_module.ensure_scene_defaults(
        scene
    )

    _require(
        settings
        .pipeline
        .initialized,
        (
            "Pipeline defaults were not "
            "initialized."
        ),
    )

    _require(
        len(
            settings.projections
        )
        == 4,
        (
            "Expected 4 default projection "
            "slots."
        ),
    )

    _require(
        tuple(
            projection.name
            for projection
            in settings.projections
        )
        == (
            "Front",
            "Right",
            "Back",
            "Top",
        ),
        (
            "Unexpected default projection "
            "layout."
        ),
    )

    pipeline = (
        settings.pipeline
    )

    _require(
        (
            pipeline
            .input_stage
            .implementation_id
        )
        == "projection-images",
        "Invalid INPUT default.",
    )

    _require(
        (
            pipeline
            .geometry_stage
            .implementation_id
        )
        == "native-visual-hull",
        "Invalid GEOMETRY default.",
    )

    _require(
        (
            pipeline
            .material_stage
            .implementation_id
        )
        == "projected-color-v1.2",
        "Invalid MATERIAL default.",
    )

    _require(
        not (
            pipeline
            .rig_stage
            .enabled
        ),
        (
            "RIG should be disabled "
            "by default."
        ),
    )

    _require(
        not (
            pipeline
            .export_stage
            .enabled
        ),
        (
            "EXPORT should be disabled "
            "by default."
        ),
    )

    registry_module = (
        importlib.import_module(
            (
                f"{module_name}."
                "core.pipeline_registry"
            )
        )
    )

    contracts_module = (
        importlib.import_module(
            (
                f"{module_name}."
                "core.pipeline_contracts"
            )
        )
    )

    registry = (
        registry_module
        .PIPELINE_REGISTRY
    )

    registered_ids = (
        registry
        .implementation_ids()
    )

    _require(
        registered_ids
        == EXPECTED_IMPLEMENTATIONS,
        (
            "Unexpected pipeline registry.\n"
            f"Expected: {EXPECTED_IMPLEMENTATIONS}\n"
            f"Actual:   {registered_ids}"
        ),
    )

    PipelineStage = (
        contracts_module
        .PipelineStage
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
        expected_id,
    ) in (
        expected_defaults
        .items()
    ):
        actual_id = (
            registry.default_id(
                stage
            )
        )

        _require(
            actual_id
            == expected_id,
            (
                "Unexpected registry default "
                f"for {stage.value}: "
                f"{actual_id!r}"
            ),
        )

    required_operator_types = (
        "BPT_OT_LoadProjectionImage",
        "BPT_OT_ImportTurntableImages",
        "BPT_OT_AddProjection",
        "BPT_OT_RemoveProjection",
        "BPT_OT_AddTurntablePreset",
        "BPT_OT_AddFrontSidePreset",
        "BPT_OT_SetPipelineImplementation",
        "BPT_OT_ResetPipelineSettings",
        "BPT_OT_RunPipeline",
        "BPT_OT_RunPipelineStage",
        "BPT_OT_GenerateCharacter",
    )

    for type_name in (
        required_operator_types
    ):
        _require(
            hasattr(
                bpy.types,
                type_name,
            ),
            (
                f"{type_name} was not "
                "registered."
            ),
        )

    required_ui_types = (
        "BPT_UL_ProjectionViews",
        "BPT_PT_MainPanel",
    )

    for type_name in (
        required_ui_types
    ):
        _require(
            hasattr(
                bpy.types,
                type_name,
            ),
            (
                f"{type_name} was not "
                "registered."
            ),
        )

    panel = getattr(
        bpy.types,
        "BPT_PT_MainPanel",
    )

    _require(
        panel.bl_space_type
        == "VIEW_3D",
        (
            "Main panel must target "
            "VIEW_3D."
        ),
    )

    _require(
        panel.bl_region_type
        == "UI",
        (
            "Main panel must target "
            "the UI region."
        ),
    )

    _require(
        panel.bl_category
        == "Meshvenn",
        (
            "Main panel category must "
            'be "Meshvenn".'
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
            "Main panel draw() "
            "is unavailable."
        ),
    )

    print(
        "Scene properties: OK"
    )

    print(
        "Pipeline defaults: OK"
    )

    print(
        "Registry: OK"
    )

    print(
        "Operators: OK"
    )

    print(
        "UI classes: OK"
    )


# ---------------------------------------------------------
# Unregistered-state checks
# ---------------------------------------------------------

def _validate_unregistered_state(
    module_name: str,
) -> None:
    _section(
        "unregistered extension"
    )

    _require(
        not hasattr(
            bpy.types.Scene,
            "bpt_settings",
        ),
        (
            "Scene.bpt_settings still exists "
            "after unregister()."
        ),
    )

    for type_name in (
        "BPT_PT_MainPanel",
        "BPT_UL_ProjectionViews",
        "BPT_OT_RunPipeline",
        "BPT_OT_RunPipelineStage",
    ):
        _require(
            not hasattr(
                bpy.types,
                type_name,
            ),
            (
                f"{type_name} still exists "
                "after unregister()."
            ),
        )

    registry_module = (
        importlib.import_module(
            (
                f"{module_name}."
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
            "Pipeline registry is not empty "
            "after unregister()."
        ),
    )

    print(
        "Scene cleanup: OK"
    )

    print(
        "RNA cleanup: OK"
    )

    print(
        "Registry cleanup: OK"
    )


if __name__ == "__main__":
    main()