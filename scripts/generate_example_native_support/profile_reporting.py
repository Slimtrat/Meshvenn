from __future__ import annotations

from .shared import COLOR_ATTRIBUTE_NAME, MATERIAL_MODE, Path, RunLogger, argparse
from .scene import export_object, scale_object_to_height

def _log_material(
    *,
    level_logger: RunLogger,
    material_stats,
    active_material_views: list,
    visibility_info: dict,
    blend_info: dict,
) -> None:
    level_logger.info(
        "projected material",
        mode=(
            MATERIAL_MODE
        ),
        views=len(
            active_material_views
        ),
        projected_vertices=(
            material_stats
            .projected_vertices
        ),
        fallback_vertices=(
            material_stats
            .fallback_vertices
        ),
        projected_fallback_vertices=(
            material_stats
            .projected_fallback_vertices
        ),
        neutral_fallback_vertices=(
            material_stats
            .neutral_fallback_vertices
        ),
        candidate_samples=(
            material_stats
            .candidate_samples
        ),
        source_rejected_samples=(
            material_stats
            .source_rejected_samples
        ),
        visible_samples=(
            material_stats
            .visible_samples
        ),
        occluded_samples=(
            material_stats
            .occluded_samples
        ),
        front_facing_samples=(
            material_stats
            .front_facing_samples
        ),
        backface_samples=(
            material_stats
            .backface_samples
        ),
        grazing_rejected_samples=(
            material_stats
            .grazing_rejected_samples
        ),
        relative_rejected_samples=(
            material_stats
            .relative_rejected_samples
        ),
        top_k_rejected_samples=(
            material_stats
            .top_k_rejected_samples
        ),
        selected_samples=(
            material_stats
            .selected_samples
        ),
        accepted_samples=(
            material_stats
            .accepted_samples
        ),
        rejected_samples=(
            material_stats
            .rejected_samples
        ),
        visibility=(
            visibility_info[
                "enabled"
            ]
        ),
        visibility_mode=(
            visibility_info[
                "mode"
            ]
        ),
        visibility_epsilon=(
            visibility_info[
                "epsilon"
            ]
        ),
        visibility_max_distance=(
            visibility_info[
                "max_distance"
            ]
        ),
        blend_mode=(
            blend_info[
                "mode"
            ]
        ),
        blend_min_facing=(
            blend_info[
                "min_facing"
            ]
        ),
        blend_facing_power=(
            blend_info[
                "facing_power"
            ]
        ),
        blend_relative_score_cutoff=(
            blend_info[
                "relative_score_cutoff"
            ]
        ),
        blend_max_contributors=(
            blend_info[
                "max_contributors"
            ]
        ),
        blend_weight_power=(
            blend_info[
                "weight_power"
            ]
        ),
    )


def _finalize_profile(
    *,
    obj,
    snapshot,
    sheet_name: str,
    level_name: str,
    scans_root: Path,
    args: argparse.Namespace,
    level_logger: RunLogger,
    active_material_views: list,
    profile_info: dict,
    material_stats,
    visibility_info: dict,
    blend_info: dict,
    stats_info: dict,
) -> None:
    with level_logger.timed(
        "scale object"
    ):
        scale_object_to_height(
            obj,
            args.target_height,
        )

    # -----------------------------------------
    # Metadata on Blender object
    # -----------------------------------------

    obj[
        "bpt_engine"
    ] = "native-cpp"

    obj[
        "bpt_mesh_mode"
    ] = (
        args.mesh_mode
    )

    obj[
        "bpt_material"
    ] = (
        MATERIAL_MODE
    )

    obj[
        "bpt_scan_level"
    ] = (
        level_name
    )

    obj[
        "bpt_projection_count"
    ] = len(
        snapshot
        .applied_views
    )

    obj[
        "bpt_material_view_count"
    ] = len(
        active_material_views
    )

    # -----------------------------------------
    # Export GLB / optional Blend
    # -----------------------------------------

    with level_logger.timed(
        "export GLB"
    ):
        export_info = (
            export_object(
                obj,
                output_dir=(
                    scans_root
                    / level_name
                ),
                stem=(
                    f"{sheet_name}_"
                    f"{level_name}"
                ),
                save_blend=(
                    not args.skip_blend
                ),
            )
        )

    # -----------------------------------------
    # Manifest profile material diagnostics
    # -----------------------------------------

    profile_info.update(
        {
            "generated": True,
            "material": {
                "mode": (
                    MATERIAL_MODE
                ),
                "attribute": (
                    COLOR_ATTRIBUTE_NAME
                ),
                "views": [
                    view.name
                    for view
                    in active_material_views
                ],
                "view_count": (
                    material_stats
                    .view_count
                ),

                # -----------------------------
                # Historical top-level metrics
                # -----------------------------

                "projected_vertices": (
                    material_stats
                    .projected_vertices
                ),
                "fallback_vertices": (
                    material_stats
                    .fallback_vertices
                ),
                "accepted_samples": (
                    material_stats
                    .accepted_samples
                ),
                "rejected_samples": (
                    material_stats
                    .rejected_samples
                ),

                # -----------------------------
                # V1.2 metrics
                # -----------------------------

                "projected_fallback_vertices": (
                    material_stats
                    .projected_fallback_vertices
                ),
                "neutral_fallback_vertices": (
                    material_stats
                    .neutral_fallback_vertices
                ),
                "candidate_samples": (
                    material_stats
                    .candidate_samples
                ),
                "source_rejected_samples": (
                    material_stats
                    .source_rejected_samples
                ),
                "visible_samples": (
                    material_stats
                    .visible_samples
                ),
                "occluded_samples": (
                    material_stats
                    .occluded_samples
                ),
                "front_facing_samples": (
                    material_stats
                    .front_facing_samples
                ),
                "backface_samples": (
                    material_stats
                    .backface_samples
                ),
                "grazing_rejected_samples": (
                    material_stats
                    .grazing_rejected_samples
                ),
                "relative_rejected_samples": (
                    material_stats
                    .relative_rejected_samples
                ),
                "top_k_rejected_samples": (
                    material_stats
                    .top_k_rejected_samples
                ),
                "selected_samples": (
                    material_stats
                    .selected_samples
                ),

                # -----------------------------
                # Configuration
                # -----------------------------

                "visibility": (
                    visibility_info
                ),
                "blend": (
                    blend_info
                ),

                # -----------------------------
                # Complete explicit statistics
                # snapshot.
                # -----------------------------

                "statistics": (
                    stats_info
                ),
            },
            **export_info,
        }
    )
