from __future__ import annotations

import math

import bpy

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from ..core.pipeline_contracts import (
    PipelinePlan,
    PipelineStage,
    PipelineStageSelection,
)

from .constants import *
from .groups import (
    BPT_PG_PipelineStageSettings,
    BPT_PG_Settings,
    PIPELINE_STAGE_DEFAULTS,
    PIPELINE_STAGE_PROPERTY_NAMES,
)

def pipeline_stage_settings(
    settings: BPT_PG_Settings,
    stage: PipelineStage,
) -> BPT_PG_PipelineStageSettings:
    """
    Return the persistent Blender settings corresponding to
    one PipelineStage.

    UI and operators use this instead of hardcoding:

        settings.pipeline.geometry_stage

    etc.
    """

    normalized_stage = (
        PipelineStage(
            stage
        )
    )

    property_name = (
        PIPELINE_STAGE_PROPERTY_NAMES[
            normalized_stage
        ]
    )

    return getattr(
        settings.pipeline,
        property_name,
    )


def ensure_pipeline_defaults(
    settings: BPT_PG_Settings,
) -> None:
    """
    Initialize generic pipeline selections exactly once.

    This is also the migration path for .blend files created
    before the generic pipeline existed.

    Implementation-specific settings such as:

        SDF Reconstruction V1
        UV Bake V2

    are Blender properties with their own defaults and do
    not need explicit migration here.
    """

    pipeline = (
        settings.pipeline
    )

    if pipeline.initialized:
        return

    for (
        stage,
        (
            implementation_id,
            enabled,
            expanded,
        ),
    ) in (
        PIPELINE_STAGE_DEFAULTS
        .items()
    ):
        stage_settings = (
            pipeline_stage_settings(
                settings,
                stage,
            )
        )

        stage_settings.implementation_id = (
            implementation_id
        )

        stage_settings.enabled = (
            enabled
        )

        stage_settings.expanded = (
            expanded
        )

    pipeline.advanced_expanded = False

    pipeline.diagnostics_expanded = False

    pipeline.initialized = True


def reset_pipeline_defaults(
    settings: BPT_PG_Settings,
) -> None:
    """
    Reset only the generic pipeline selection state.

    Projection images and implementation-specific settings
    are deliberately preserved.
    """

    pipeline = (
        settings.pipeline
    )

    pipeline.initialized = False

    ensure_pipeline_defaults(
        settings
    )


def set_pipeline_implementation(
    settings: BPT_PG_Settings,
    stage: PipelineStage,
    implementation_id: str,
) -> None:
    """
    Persist one user-selected pipeline implementation.

    Empty identifiers remain valid here because optional
    stages such as RIG and EXPORT may have no implementation
    selected.
    """

    stage_settings = (
        pipeline_stage_settings(
            settings,
            stage,
        )
    )

    stage_settings.implementation_id = (
        str(
            implementation_id
        ).strip()
    )


def get_pipeline_implementation(
    settings: BPT_PG_Settings,
    stage: PipelineStage,
) -> str:
    return (
        pipeline_stage_settings(
            settings,
            stage,
        )
        .implementation_id
        .strip()
    )


# =========================================================
# PipelinePlan bridge
# =========================================================

def build_pipeline_plan(
    settings: BPT_PG_Settings,
) -> PipelinePlan:
    """
    Convert persistent Blender state into the pure Python
    PipelinePlan consumed by PipelineRunner.
    """

    ensure_pipeline_defaults(
        settings
    )

    selections: list[
        PipelineStageSelection
    ] = []

    for stage in (
        PipelineStage
    ):
        stage_settings = (
            pipeline_stage_settings(
                settings,
                stage,
            )
        )

        implementation_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        # -------------------------------------------------
        # Disabled optional stage with no remembered
        # implementation does not participate.
        # -------------------------------------------------

        if (
            not implementation_id
            and not stage_settings.enabled
        ):
            continue

        # -------------------------------------------------
        # Enabled stage without implementation is a genuine
        # configuration error.
        # -------------------------------------------------

        if (
            stage_settings.enabled
            and not implementation_id
        ):
            raise ValueError(
                (
                    f'Pipeline stage "{stage.value}" '
                    "is enabled but has no "
                    "implementation selected."
                )
            )

        # -------------------------------------------------
        # Disabled stage with a remembered implementation is
        # retained as disabled so toggling it does not erase
        # the user's selection.
        # -------------------------------------------------

        if implementation_id:
            selections.append(
                PipelineStageSelection(
                    stage=stage,

                    implementation_id=(
                        implementation_id
                    ),

                    enabled=(
                        stage_settings
                        .enabled
                    ),
                )
            )

    return PipelinePlan(
        selections=tuple(
            selections
        )
    )
