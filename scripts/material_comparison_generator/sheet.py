from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from core.native_scan import NativeScanner
from scripts.generate_example_native import (
    extract_sheet,
    material_views_for_snapshot,
    prepare_material_views,
    prepare_projections,
)
from scripts.run_logger import RunLogger

from .adapters import build_projection_source
from .config import PipelineRuntime
from .io import write_json
from .variant import generate_variant


# =========================================================
# One sheet
# =========================================================

def process_sheet(
    runtime: PipelineRuntime,
    *,
    sheet_path: Path,
    output_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> dict:
    sheet_name = (
        sheet_path.stem
    )

    sheet_output = (
        output_root
        / sheet_name
    )

    # Comparison output is disposable. Removing the previous
    # sheet avoids stale implementation/profile files.
    if sheet_output.exists():
        shutil.rmtree(
            sheet_output
        )

    sheet_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    extracted_dir = (
        sheet_output
        / "source"
    )

    manifest = {
        "sheet": (
            sheet_name
        ),

        "source": str(
            sheet_path
        ),

        "resolution": (
            args.resolution
        ),

        "mesh_mode": (
            args.mesh_mode
        ),

        "profiles": {},

        "implementations": list(
            args.implementations
        ),

        "uv_bake_preview": {
            "texture_size": (
                args.texture_size
            ),
            "padding_pixels": (
                args.padding
            ),
            "samples_per_axis": (
                args.samples_per_axis
            ),
            "uv_layer_name": (
                args.uv_layer_name
            ),
            "island_margin": (
                args.island_margin
            ),
            "angle_limit_degrees": (
                args.angle_limit
            ),
        },
    }

    with logger.section(
        f"sheet {sheet_name}"
    ):
        # -------------------------------------------------
        # Extract source sheet.
        # -------------------------------------------------

        with logger.timed(
            "extract source views"
        ):
            (
                extracted_views,
                source_manifest,
            ) = extract_sheet(
                sheet_path,
                extracted_dir,
                white_threshold=(
                    args
                    .sheet_white_threshold
                ),
                alpha_threshold=(
                    args.threshold
                ),
                logger=(
                    logger.child()
                ),
            )

        manifest[
            "source_manifest"
        ] = (
            source_manifest
        )

        # -------------------------------------------------
        # Prepare geometry + material inputs once.
        # -------------------------------------------------

        with logger.timed(
            "prepare projections"
        ):
            projections = (
                prepare_projections(
                    extracted_views,
                    logger=(
                        logger.child()
                    ),
                )
            )

        with logger.timed(
            "prepare material views"
        ):
            material_views = (
                prepare_material_views(
                    extracted_views,
                    logger=(
                        logger.child()
                    ),
                )
            )

        # -------------------------------------------------
        # Geometry is reconstructed ONCE.
        #
        # Both MATERIAL implementations receive snapshots
        # from this exact same scan.
        # -------------------------------------------------

        scanner = (
            NativeScanner()
        )

        with logger.timed(
            "native scan"
        ):
            scan_result = (
                scanner.scan_levels(
                    projections,
                    resolution=(
                        args.resolution
                    ),
                    levels=(
                        args.profiles
                    ),
                    symmetry_x=(
                        args.symmetry_x
                    ),
                    thread_count=(
                        args.thread_count
                    ),
                    build_meshes=True,
                    voxel_size=(
                        args.voxel_size
                    ),
                    center_xy=True,
                    mesh_mode=(
                        args.mesh_mode
                    ),
                )
            )

        manifest[
            "available_views"
        ] = list(
            scan_result
            .available_views
        )

        manifest[
            "requested_profiles"
        ] = list(
            scan_result
            .requested_levels
        )

        # -------------------------------------------------
        manifest["view_diagnostics"] = [
            view.as_dict() for view in scan_result.view_diagnostics
        ]
        for view in scan_result.view_diagnostics:
            if view.status != "ok":
                logger.warning("Projection reduced visual hull", **view.as_dict())
        # Compare MATERIAL implementations.
        # -------------------------------------------------

        for (
            level_name,
            snapshot,
        ) in (
            scan_result
            .snapshots
            .items()
        ):
            level_info = {
                "generated": False,

                "views": list(
                    snapshot
                    .applied_views
                ),

                "occupied_voxels": (
                    snapshot
                    .volume
                    .occupied_count
                ),

                "implementations": {},
            }

            manifest[
                "profiles"
            ][
                level_name
            ] = (
                level_info
            )

            if snapshot.mesh is None:
                level_info[
                    "reason"
                ] = (
                    "Native scan produced no mesh."
                )

                continue

            active_material_views = (
                material_views_for_snapshot(
                    material_views,
                    list(
                        snapshot
                        .applied_views
                    ),
                )
            )

            if not active_material_views:
                level_info[
                    "reason"
                ] = (
                    "No material views are "
                    "available for this profile."
                )

                continue

            source = (
                build_projection_source(
                    runtime,
                    extracted_views=(
                        extracted_views
                    ),
                    projections=projections,
                    material_views=(
                        material_views
                    ),
                    applied_views=(
                        snapshot
                        .applied_views
                    ),
                    alpha_threshold=(
                        args.threshold
                    ),
                )
            )

            for implementation_id in (
                args.implementations
            ):
                variant_logger = (
                    logger.child()
                )

                try:
                    with (
                        variant_logger
                        .section(
                            (
                                f"{level_name} / "
                                f"{implementation_id}"
                            )
                        )
                    ):
                        info = (
                            generate_variant(
                                runtime,
                                implementation_id=(
                                    implementation_id
                                ),
                                sheet_name=(
                                    sheet_name
                                ),
                                level_name=(
                                    level_name
                                ),
                                snapshot=(
                                    snapshot
                                ),
                                source=source,
                                output_root=(
                                    output_root
                                ),
                                args=args,
                                logger=(
                                    variant_logger
                                ),
                            )
                        )

                    level_info[
                        "implementations"
                    ][
                        implementation_id
                    ] = info

                except Exception as exc:
                    level_info[
                        "implementations"
                    ][
                        implementation_id
                    ] = {
                        "generated": False,

                        "error": str(
                            exc
                        ),

                        "exception_type": (
                            type(exc).__name__
                        ),
                    }

                    variant_logger.error(
                        "variant failed",
                        implementation=(
                            implementation_id
                        ),
                        error=str(
                            exc
                        ),
                    )

                    if (
                        not args
                        .continue_on_error
                    ):
                        raise

            level_info[
                "generated"
            ] = any(
                bool(
                    implementation_info
                    .get(
                        "generated",
                        False,
                    )
                )
                for implementation_info
                in (
                    level_info[
                        "implementations"
                    ]
                    .values()
                )
            )

    manifest_path = (
        sheet_output
        / "comparison.json"
    )

    write_json(
        manifest_path,
        manifest,
    )

    logger.success(
        "sheet comparison written",
        path=str(
            manifest_path
        ),
    )

    return manifest
