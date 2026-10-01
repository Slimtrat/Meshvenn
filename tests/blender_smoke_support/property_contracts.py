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
    # Emulate a .blend saved before the Motion and Export stages existed.
    # New pointer properties use their RNA defaults even when the legacy
    # pipeline was already initialized.
    pipeline = settings.pipeline
    pipeline.initialized = True
    pipeline.schema_version = 0
    pipeline.motion_stage.implementation_id = ""
    pipeline.motion_stage.enabled = True
    pipeline.motion_stage.expanded = True
    pipeline.export_stage.implementation_id = ""
    pipeline.export_stage.enabled = True
    pipeline.export_stage.expanded = True
    properties_module.ensure_pipeline_defaults(settings)
    _require(
        pipeline.schema_version == 3
        and pipeline.motion_stage.implementation_id
        == "canonical-motion-retarget-v1"
        and not pipeline.motion_stage.enabled
        and not pipeline.motion_stage.expanded
        and pipeline.export_stage.implementation_id == "glb-export-v1"
        and not pipeline.export_stage.enabled
        and not pipeline.export_stage.expanded,
        "Legacy .blend Motion/Export migration is unsafe.",
    )

    # A schema-v1 file already owns its Motion selection. Export migration
    # must preserve it and any nonempty third-party Export selection.
    pipeline.schema_version = 1
    pipeline.motion_stage.implementation_id = "third-party-motion"
    pipeline.motion_stage.enabled = True
    pipeline.motion_stage.expanded = True
    pipeline.export_stage.implementation_id = "third-party-export"
    pipeline.export_stage.enabled = True
    pipeline.export_stage.expanded = True
    properties_module.ensure_pipeline_defaults(settings)
    _require(
        pipeline.schema_version == 3
        and pipeline.motion_stage.implementation_id == "third-party-motion"
        and pipeline.motion_stage.enabled
        and pipeline.motion_stage.expanded
        and pipeline.export_stage.implementation_id == "third-party-export"
        and pipeline.export_stage.enabled
        and pipeline.export_stage.expanded,
        "Schema-v1 Export migration did not preserve existing selections.",
    )

    # Restore production defaults for the remaining smoke assertions.
    pipeline.motion_stage.implementation_id = "canonical-motion-retarget-v1"
    pipeline.motion_stage.enabled = False
    pipeline.motion_stage.expanded = False
    pipeline.export_stage.implementation_id = "glb-export-v1"
    pipeline.export_stage.enabled = False
    pipeline.export_stage.expanded = False



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

    for projection in settings.projections:
        _require(
            (projection.alignment_offset_u, projection.alignment_offset_v,
             projection.alignment_scale) == (0.0, 0.0, 1.0),
            "Default alignment must leave existing projections unchanged.",
        )

    print(
        "Default projections: OK"
    )


# =========================================================
# Pipeline defaults
# =========================================================

def _validate_pipeline_defaults(
    package_name: str,
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
        (
            pipeline.rig_stage.implementation_id,
            "canonical-biped-v1",
            "RIG",
        ),
        (
            pipeline.motion_stage.implementation_id,
            "canonical-motion-retarget-v1",
            "MOTION",
        ),
        (
            pipeline.export_stage.implementation_id,
            "glb-export-v1",
            "EXPORT",
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
        not pipeline.motion_stage.enabled,
        "MOTION must be disabled.",
    )

    _require(
        not pipeline.export_stage.enabled,
        "EXPORT must be disabled.",
    )


    _require(
        pipeline.schema_version == 3,
        "Pipeline settings schema was not migrated.",
    )

    _require(
        settings.motion_source_path == "",
        "Default Motion source path must be empty.",
    )

    _require(
        settings.glb_input_path == ""
        and settings.glb_normalized_extent == 2.0,
        "Default GLB-first settings are incorrect.",
    )

    _require(
        settings.export_output_path == "",
        "Default Export output path must be empty.",
    )

    _require(
        not settings.export_overwrite_existing,
        "Export overwrite must default to disabled.",
    )

    runtime_module = importlib.import_module(
        f"{package_name}.operators.runtime_execution"
    )
    default_context = runtime_module._new_pipeline_context(bpy.context)
    _require(
        default_context.metadata["glb_input_path"] == ""
        and default_context.metadata["glb_normalized_extent"] == 2.0
        and default_context.metadata["export_output_path"] == ""
        and default_context.metadata["export_overwrite_existing"] is False,
        "Default Export runtime metadata is incorrect.",
    )

    settings.glb_input_path = "assets/source.glb"
    settings.glb_normalized_extent = 3.5
    settings.export_output_path = "exports/character.glb"
    settings.export_overwrite_existing = True
    configured_context = runtime_module._new_pipeline_context(bpy.context)
    _require(
        configured_context.metadata["glb_input_path"]
        == bpy.path.abspath(settings.glb_input_path)
        and configured_context.metadata["glb_normalized_extent"] == 3.5
        and configured_context.metadata["export_output_path"]
        == bpy.path.abspath(settings.export_output_path)
        and configured_context.metadata["export_overwrite_existing"] is True,
        "Configured Export runtime metadata was not normalized through bpy.path.abspath.",
    )
    settings.glb_input_path = ""
    settings.glb_normalized_extent = 2.0
    settings.export_output_path = ""
    settings.export_overwrite_existing = False

    for stage_settings in (
        pipeline.input_stage,
        pipeline.geometry_stage,
        pipeline.rig_stage,
        pipeline.motion_stage,
    ):
        stage_settings.enabled = False
    toggle_result = bpy.ops.bpt.set_pipeline_stage_enabled(
        stage="motion",
        enabled=True,
    )
    _require(
        "FINISHED" in toggle_result
        and pipeline.input_stage.enabled
        and pipeline.geometry_stage.enabled
        and pipeline.rig_stage.enabled
        and pipeline.motion_stage.enabled,
        "Enabling Motion did not enable its complete dependency chain.",
    )
    disable_result = bpy.ops.bpt.set_pipeline_stage_enabled(
        stage="rig",
        enabled=False,
    )
    _require(
        "FINISHED" in disable_result
        and not pipeline.rig_stage.enabled
        and not pipeline.motion_stage.enabled,
        "Disabling Rig did not disable its Motion dependent.",
    )
    pipeline.input_stage.enabled = False
    pipeline.geometry_stage.enabled = False
    pipeline.export_stage.enabled = False
    export_toggle_result = bpy.ops.bpt.set_pipeline_stage_enabled(
        stage="export",
        enabled=True,
    )
    _require(
        "FINISHED" in export_toggle_result
        and pipeline.input_stage.enabled
        and pipeline.geometry_stage.enabled
        and pipeline.export_stage.enabled
        and not pipeline.rig_stage.enabled
        and not pipeline.motion_stage.enabled,
        "Enabling Export did not enable exactly its Geometry/Input dependencies.",
    )
    pipeline.export_stage.enabled = False

    preset_result = bpy.ops.bpt.use_glb_first_pipeline()
    _require(
        "FINISHED" in preset_result
        and pipeline.input_stage.implementation_id == "glb-file-v1"
        and pipeline.geometry_stage.implementation_id
        == "glb-preserved-geometry-v1"
        and pipeline.rig_stage.implementation_id == "glb-source-rig-v1"
        and pipeline.motion_stage.implementation_id == "glb-source-motion-v1"
        and pipeline.input_stage.enabled
        and pipeline.geometry_stage.enabled
        and not pipeline.material_stage.enabled
        and pipeline.rig_stage.enabled
        and pipeline.motion_stage.enabled
        and pipeline.export_stage.enabled,
        "GLB source-preservation pipeline preset is incomplete.",
    )
    canonical_result = bpy.ops.bpt.use_glb_canonical_pipeline()
    _require(
        "FINISHED" in canonical_result
        and pipeline.geometry_stage.implementation_id
        == "glb-normalized-geometry-v1"
        and pipeline.rig_stage.implementation_id == "canonical-biped-v1"
        and pipeline.motion_stage.implementation_id
        == "canonical-motion-retarget-v1",
        "GLB canonicalization pipeline preset is incomplete.",
    )
    properties_module = importlib.import_module(f"{package_name}.properties")
    properties_module.reset_pipeline_defaults(settings)

    print(
        "Pipeline defaults: OK"
    )

    print(
        "  GEOMETRY native-visual-hull [default]"
    )

    print(
        "           sdf-reconstruction-v1 [available]"
    )
