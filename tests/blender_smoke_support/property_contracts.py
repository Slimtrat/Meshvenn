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
