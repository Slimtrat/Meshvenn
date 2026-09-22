from __future__ import annotations

import argparse
from pathlib import Path

from core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from scripts.generate_example_native import (
    clear_scene,
    export_object,
    scale_object_to_height,
)
from scripts.run_logger import RunLogger

from .adapters import (
    build_geometry_output,
    build_material_settings,
    execute_material,
)
from .config import PipelineRuntime
from .io import json_safe, write_json
from .lifecycle import cleanup_object


# =========================================================
# One variant
# =========================================================

def generate_variant(
    runtime: PipelineRuntime,
    *,
    implementation_id: str,
    sheet_name: str,
    level_name: str,
    snapshot,
    source,
    output_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> dict:
    clear_scene()

    obj = None

    try:
        object_name = (
            "MeshvennCompare_"
            f"{sheet_name}_"
            f"{level_name}_"
            f"{implementation_id}"
        )

        with logger.timed(
            "inject mesh"
        ):
            obj = (
                create_blender_mesh_from_native(
                    snapshot.mesh,
                    mesh_name=object_name,
                    object_name=object_name,
                )
            )

        with logger.timed(
            "shade smooth"
        ):
            shade_smooth_native_object(
                obj
            )

        geometry = (
            build_geometry_output(
                runtime,
                obj=obj,
                snapshot=snapshot,
                source=source,
                args=args,
            )
        )

        settings = (
            build_material_settings(
                args
            )
        )

        logger.info(
            "material implementation",
            implementation=(
                implementation_id
            ),
        )

        (
            material_result,
            material_elapsed,
            availability,
        ) = (
            execute_material(
                runtime,
                implementation_id=(
                    implementation_id
                ),
                geometry=geometry,
                settings=settings,
            )
        )

        # -------------------------------------------------
        # Projection coordinates must remain native until
        # MATERIAL has completely finished.
        # -------------------------------------------------

        with logger.timed(
            "normalize height"
        ):
            scale_object_to_height(
                obj,
                args.target_height,
            )

        obj[
            "meshvenn_compare"
        ] = True

        obj[
            "meshvenn_compare_sheet"
        ] = sheet_name

        obj[
            "meshvenn_compare_profile"
        ] = level_name

        obj[
            "meshvenn_compare_material"
        ] = implementation_id

        variant_dir = (
            output_root
            / sheet_name
            / level_name
            / implementation_id
        )

        variant_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with logger.timed(
            "export GLB"
        ):
            export_info = (
                export_object(
                    obj,
                    output_dir=(
                        variant_dir
                    ),
                    stem="model",
                    save_blend=bool(
                        args.save_blend
                    ),
                )
            )

        payload = (
            material_result.payload
        )

        material_specific = {}

        # -------------------------------------------------
        # UV Bake diagnostics
        # -------------------------------------------------

        bake_result = getattr(
            payload,
            "bake_result",
            None,
        )

        if bake_result is not None:
            stats = (
                bake_result.stats
            )

            material_specific[
                "uv_bake"
            ] = {
                "texture_width": (
                    bake_result
                    .texture
                    .width
                ),
                "texture_height": (
                    bake_result
                    .texture
                    .height
                ),
                "triangle_count": (
                    stats.triangle_count
                ),
                "rasterized_triangles": (
                    stats
                    .rasterized_triangles
                ),
                "degenerate_triangles": (
                    stats
                    .degenerate_triangles
                ),
                "covered_pixels": (
                    stats.covered_pixels
                ),
                "padded_pixels": (
                    stats.padded_pixels
                ),
                "overlap_pixels": (
                    stats.overlap_pixels
                ),
                "surface_samples": (
                    stats.surface_samples
                ),
                "fallback_samples": (
                    stats.fallback_samples
                ),
                "selected_source_samples": (
                    stats
                    .selected_source_samples
                ),
                "coverage_ratio": (
                    stats.coverage_ratio
                ),
            }

        # -------------------------------------------------
        # Projected Color diagnostics
        # -------------------------------------------------

        projected_stats = getattr(
            payload,
            "stats",
            None,
        )

        if projected_stats is not None:
            material_specific[
                "projected_color"
            ] = {
                "vertex_count": (
                    projected_stats
                    .vertex_count
                ),
                "view_count": (
                    projected_stats
                    .view_count
                ),
                "projected_vertices": (
                    projected_stats
                    .projected_vertices
                ),
                "fallback_vertices": (
                    projected_stats
                    .fallback_vertices
                ),
                "visible_samples": (
                    projected_stats
                    .visible_samples
                ),
                "occluded_samples": (
                    projected_stats
                    .occluded_samples
                ),
                "selected_samples": (
                    projected_stats
                    .selected_samples
                ),
            }

        info = {
            "generated": True,

            "implementation": (
                implementation_id
            ),

            "availability": {
                "state": str(
                    availability.state.value
                ),
                "reason": (
                    availability.reason
                ),
                "details": json_safe(
                    availability.details
                ),
            },

            "material_seconds": (
                material_elapsed
            ),

            "result": {
                "message": (
                    material_result
                    .message
                ),
                "metrics": json_safe(
                    material_result
                    .metrics
                ),
                "metadata": json_safe(
                    material_result
                    .metadata
                ),
            },

            "geometry": {
                "vertices": len(
                    obj.data.vertices
                ),
                "faces": len(
                    obj.data.polygons
                ),
                "dimensions": [
                    float(value)
                    for value
                    in obj.dimensions
                ],
                "mesh_mode": (
                    args.mesh_mode
                ),
                "occupied_voxels": (
                    snapshot
                    .volume
                    .occupied_count
                ),
            },

            **material_specific,

            "export": (
                export_info
            ),
        }

        write_json(
            (
                variant_dir
                / "variant.json"
            ),
            info,
        )

        logger.success(
            "variant generated",
            implementation=(
                implementation_id
            ),
            elapsed=(
                material_elapsed
            ),
            glb=(
                export_info[
                    "glb"
                ]
            ),
        )

        return info

    finally:
        cleanup_object(
            obj
        )
