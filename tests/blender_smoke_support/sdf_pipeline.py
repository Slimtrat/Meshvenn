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
        properties_module.set_pipeline_implementation(
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
        properties_module.set_pipeline_implementation(
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
