from __future__ import annotations

import argparse
import time
from types import SimpleNamespace

import bpy

from .config import PipelineRuntime
from .io import json_safe


# =========================================================
# Pipeline source adapter
# =========================================================

def build_projection_source(
    runtime: PipelineRuntime,
    *,
    extracted_views,
    projections: dict,
    material_views: dict,
    applied_views,
    alpha_threshold: float,
):
    """
    Build the real ProjectionImagesOutput contract expected
    downstream by NativeVisualHullOutput.

    The extraction/native scan still comes from the existing
    diagnostic script, but MATERIAL receives the same
    contract as the product pipeline.
    """

    extracted_by_name = {
        view.name: view
        for view
        in extracted_views
    }

    prepared = []

    for view_name in applied_views:
        extracted = (
            extracted_by_name.get(
                view_name
            )
        )

        native_projection = (
            projections.get(
                view_name
            )
        )

        material_view = (
            material_views.get(
                view_name
            )
        )

        if extracted is None:
            raise RuntimeError(
                (
                    "Missing extracted view: "
                    f"{view_name}"
                )
            )

        if native_projection is None:
            raise RuntimeError(
                (
                    "Missing NativeProjection: "
                    f"{view_name}"
                )
            )

        if material_view is None:
            raise RuntimeError(
                (
                    "Missing ProjectedMaterialView: "
                    f"{view_name}"
                )
            )

        prepared.append(
            runtime
            .projection_images
            .PreparedProjectionView(
                name=(
                    extracted.name
                ),
                image_name=(
                    extracted.path.name
                ),
                width=(
                    extracted.mask.width
                ),
                height=(
                    extracted.mask.height
                ),
                azimuth_degrees=(
                    extracted
                    .azimuth_degrees
                ),
                elevation_degrees=(
                    extracted
                    .elevation_degrees
                ),
                flip_x=False,
                weight=1.0,
                mask=(
                    extracted.mask
                ),
                native_projection=(
                    native_projection
                ),
                material_view=(
                    material_view
                ),
            )
        )

    if not prepared:
        raise RuntimeError(
            (
                "No prepared views remain "
                "for this profile."
            )
        )

    return (
        runtime
        .projection_images
        .ProjectionImagesOutput(
            views=tuple(
                prepared
            ),
            alpha_threshold=float(
                alpha_threshold
            ),
            enabled_projection_count=len(
                prepared
            ),
            missing_image_count=0,
        )
    )


# =========================================================
# Geometry adapter
# =========================================================

def build_geometry_output(
    runtime: PipelineRuntime,
    *,
    obj: bpy.types.Object,
    snapshot,
    source,
    args: argparse.Namespace,
):
    """
    Represent the exact same native snapshot through the
    production NativeVisualHullOutput contract.

    We intentionally bake MATERIAL before target-height
    normalization, matching the real pipeline coordinate
    convention.
    """

    return (
        runtime
        .native_visual_hull
        .NativeVisualHullOutput(
            blender_object=obj,

            volume=(
                snapshot.volume
            ),

            native_mesh=(
                snapshot.mesh
            ),

            source=source,

            resolution=int(
                args.resolution
            ),

            symmetry_x=bool(
                args.symmetry_x
            ),

            thread_count=int(
                args.thread_count
            ),

            mesh_mode=str(
                args.mesh_mode
            ),

            voxel_size=float(
                args.voxel_size
            ),

            center_xy=True,

            normalized_height=False,

            target_height=None,

            normalization_scale=1.0,
        )
    )


# =========================================================
# Material configuration
# =========================================================

def build_material_settings(
    args: argparse.Namespace,
):
    """
    Lightweight settings object consumed by both production
    MATERIAL implementations.

    Shared V1.2 projection configuration is kept identical
    between both variants.
    """

    return SimpleNamespace(
        # -------------------------------------------------
        # Shared projected-color configuration
        # -------------------------------------------------

        material_enable_visibility=True,

        material_allow_backface_fallback=True,

        material_min_facing=0.10,

        material_facing_power=2.0,

        material_relative_score_cutoff=0.20,

        material_max_contributors=3,

        material_weight_power=1.5,

        # -------------------------------------------------
        # UV Bake
        # -------------------------------------------------

        uv_bake_texture_size=int(
            args.texture_size
        ),

        uv_bake_padding_pixels=int(
            args.padding
        ),

        uv_bake_samples_per_axis=int(
            args.samples_per_axis
        ),

        uv_bake_uv_layer_name=str(
            args.uv_layer_name
        ),

        uv_bake_island_margin=float(
            args.island_margin
        ),

        uv_bake_angle_limit_degrees=float(
            args.angle_limit
        ),

        # Force production Smart UV generation.
        uv_bake_reuse_existing_uv=False,
    )


# =========================================================
# Implementation
# =========================================================

def create_material_implementation(
    runtime: PipelineRuntime,
    implementation_id: str,
):
    if (
        implementation_id
        == "projected-color-v1.2"
    ):
        return (
            runtime
            .projected_color
            .ProjectedColorImplementation()
        )

    if (
        implementation_id
        == "uv-bake-v2"
    ):
        return (
            runtime
            .uv_bake
            .UVBakeImplementation()
        )

    raise ValueError(
        (
            "Unsupported MATERIAL implementation: "
            f"{implementation_id}"
        )
    )


def execute_material(
    runtime: PipelineRuntime,
    *,
    implementation_id: str,
    geometry,
    settings,
):
    PipelineContext = (
        runtime
        .contracts
        .PipelineContext
    )

    PipelineStage = (
        runtime
        .contracts
        .PipelineStage
    )

    context = PipelineContext(
        scene=(
            bpy.context.scene
        ),
        settings=settings,
    )

    context.set_output(
        PipelineStage.GEOMETRY,
        geometry,
    )

    implementation = (
        create_material_implementation(
            runtime,
            implementation_id,
        )
    )

    availability = (
        implementation
        .availability(
            context
        )
    )

    if not availability.available:
        raise RuntimeError(
            (
                f"{implementation_id} unavailable: "
                f"{availability.reason}. "
                f"{json_safe(availability.details)}"
            )
        )

    started_at = (
        time.perf_counter()
    )

    result = (
        implementation.execute(
            context
        )
    )

    elapsed = (
        time.perf_counter()
        - started_at
    )

    if not result.success:
        raise RuntimeError(
            (
                f"{implementation_id} failed: "
                f"{result.message}"
            )
        )

    return (
        result,
        elapsed,
        availability,
    )
