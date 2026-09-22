from __future__ import annotations

from .shared import BLEND_MODE, MATERIAL_MODE, RunLogger, VISIBILITY_MODE, apply_projected_material, argparse, create_blender_mesh_from_native, shade_smooth_native_object
from .projection import material_blend_manifest, material_stats_manifest, material_views_for_snapshot, material_visibility_manifest
from .scene import clear_scene

def _initial_profile_info(
    snapshot,
    material_views: dict,
    args: argparse.Namespace,
) -> None:
    active_material_views = (
        material_views_for_snapshot(
            material_views,
            list(
                snapshot
                .applied_views
            ),
        )
    )

    profile_info = {
        "generated": False,
        "mesh_mode": (
            args.mesh_mode
        ),
        "material_mode": (
            MATERIAL_MODE
        ),
        "material_visibility_mode": (
            VISIBILITY_MODE
        ),
        "material_blend_mode": (
            BLEND_MODE
        ),
        "views": list(
            snapshot
            .applied_views
        ),
        "material_views": [
            view.name
            for view
            in active_material_views
        ],
        "occupied_voxels": (
            snapshot
            .volume
            .occupied_count
        ),
        "bounds": (
            list(
                snapshot
                .volume
                .bounds
            )
            if (
                snapshot
                .volume
                .bounds
            )
            else None
        ),
    }
    return active_material_views, profile_info


def _create_mesh_and_material(
    *,
    snapshot,
    sheet_name: str,
    level_name: str,
    active_material_views: list,
    args: argparse.Namespace,
    level_logger: RunLogger,
) -> None:
    clear_scene()

    # -----------------------------------------
    # Inject native mesh
    # -----------------------------------------

    with level_logger.timed(
        "inject native mesh"
    ):
        obj = (
            create_blender_mesh_from_native(
                snapshot.mesh,
                mesh_name=(
                    f"BPT_"
                    f"{sheet_name}_"
                    f"{level_name}"
                ),
                object_name=(
                    f"BPT_"
                    f"{sheet_name}_"
                    f"{level_name}"
                ),
            )
        )

    # -----------------------------------------
    # Smooth shading first.
    #
    # Projected material uses vertex normals for
    # source-view confidence.
    # -----------------------------------------

    with level_logger.timed(
        "shade smooth"
    ):
        shade_smooth_native_object(
            obj
        )

    # -----------------------------------------
    # Project source RGB onto mesh.
    #
    # IMPORTANT:
    #
    # This happens before target-height scaling,
    # while positions remain in native
    # reconstruction coordinates.
    #
    # V1.1:
    #   visibility / occlusion
    #
    # V1.2:
    #   adaptive confidence blend
    #   + grazing rejection
    #   + relative cutoff
    #   + top-K
    #   + weight sharpening
    # -----------------------------------------

    if not active_material_views:
        raise RuntimeError(
            (
                "No projected material "
                f"views available for "
                f"{sheet_name}/{level_name}."
            )
        )

    with level_logger.timed(
        "project material"
    ):
        material_stats = (
            apply_projected_material(
                obj,
                active_material_views,
                volume_width=(
                    snapshot
                    .volume
                    .width
                ),
                volume_depth=(
                    snapshot
                    .volume
                    .depth
                ),
                volume_height=(
                    snapshot
                    .volume
                    .height
                ),
                voxel_size=(
                    args.voxel_size
                ),
                center_xy=True,
                facing_power=2.0,
                allow_backface_fallback=True,
                enable_visibility=True,
            )
        )

    visibility_info = (
        material_visibility_manifest(
            obj
        )
    )

    blend_info = (
        material_blend_manifest(
            obj
        )
    )

    stats_info = (
        material_stats_manifest(
            material_stats
        )
    )
    return obj, material_stats, visibility_info, blend_info, stats_info
