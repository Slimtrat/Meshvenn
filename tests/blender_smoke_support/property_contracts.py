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
    # Emulate a .blend saved before the Motion stage existed. New pointer
    # properties use their RNA defaults (enabled and empty), even when the
    # legacy pipeline was already initialized.
    pipeline = settings.pipeline
    pipeline.initialized = True
    pipeline.schema_version = 0
    pipeline.motion_stage.implementation_id = ""
    pipeline.motion_stage.enabled = True
    pipeline.motion_stage.expanded = True
    properties_module.ensure_pipeline_defaults(settings)
    _require(
        pipeline.schema_version == 1
        and pipeline.motion_stage.implementation_id
        == "canonical-motion-retarget-v1"
        and not pipeline.motion_stage.enabled
        and not pipeline.motion_stage.expanded,
        "Legacy .blend Motion migration is unsafe.",
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
        pipeline.schema_version == 1,
        "Pipeline settings schema was not migrated.",
    )

    _require(
        settings.motion_source_path == "",
        "Default Motion source path must be empty.",
    )

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

    print(
        "Pipeline defaults: OK"
    )

    print(
        "  GEOMETRY native-visual-hull [default]"
    )

    print(
        "           sdf-reconstruction-v1 [available]"
    )
