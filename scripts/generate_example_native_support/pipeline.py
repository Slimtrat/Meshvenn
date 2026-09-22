from __future__ import annotations

from .shared import BLEND_MODE, MATERIAL_MODE, NativeScanner, Path, RunLogger, VISIBILITY_MODE, argparse, json
from .extraction import extract_sheet
from .profile import _process_profile
from .projection import prepare_material_views, prepare_projections

def process_sheet(
    sheet_path: Path,
    generated_root: Path,
    args: argparse.Namespace,
    *,
    logger: RunLogger,
) -> None:
    sheet_name = (
        sheet_path.stem
    )

    sheet_root = (
        generated_root
        / sheet_name
    )

    extracted_dir = (
        sheet_root
        / "extracted"
    )

    scans_root = (
        sheet_root
        / "scans"
    )

    sheet_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    with logger.section(
        f"sheet {sheet_name}",
        source=str(
            sheet_path
        ),
    ):
        # -------------------------------------------------
        # Extract source views
        # -------------------------------------------------

        with logger.timed(
            "extract sheet"
        ):
            (
                views,
                manifest,
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

        # -------------------------------------------------
        # Geometry inputs
        # -------------------------------------------------

        with logger.timed(
            "prepare masks"
        ):
            projections = (
                prepare_projections(
                    views,
                    logger=(
                        logger.child()
                    ),
                )
            )

        # -------------------------------------------------
        # Appearance inputs
        # -------------------------------------------------

        with logger.timed(
            "prepare material views"
        ):
            material_views = (
                prepare_material_views(
                    views,
                    logger=(
                        logger.child()
                    ),
                )
            )

        logger.info(
            "native scan input",
            views=", ".join(
                projections.keys()
            ),
            resolution=(
                args.resolution
            ),
            threads=(
                args.thread_count
            ),
            mesh_mode=(
                args.mesh_mode
            ),
            material_mode=(
                MATERIAL_MODE
            ),
            visibility_mode=(
                VISIBILITY_MODE
            ),
            blend_mode=(
                BLEND_MODE
            ),
        )

        scanner = (
            NativeScanner()
        )

        # -------------------------------------------------
        # Native reconstruction
        # -------------------------------------------------

        with logger.timed(
            "native scan"
        ):
            result = (
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

        # -------------------------------------------------
        # Manifest global information
        # -------------------------------------------------

        manifest[
            "mesh_mode"
        ] = (
            args.mesh_mode
        )

        manifest[
            "material_mode"
        ] = (
            MATERIAL_MODE
        )

        manifest[
            "material_visibility_mode"
        ] = (
            VISIBILITY_MODE
        )

        manifest[
            "material_blend_mode"
        ] = (
            BLEND_MODE
        )

        manifest[
            "material_views"
        ] = list(
            material_views.keys()
        )

        manifest[
            "requested_profiles"
        ] = list(
            result.requested_levels
        )

        manifest[
            "available_views"
        ] = list(
            result.available_views
        )

        manifest[
            "profiles"
        ] = {}

        # -------------------------------------------------
        # Build one Blender object per profile
        # -------------------------------------------------
        for level_name, snapshot in result.snapshots.items():
            _process_profile(
                sheet_name=sheet_name, level_name=level_name,
                snapshot=snapshot, material_views=material_views,
                manifest=manifest, scans_root=scans_root,
                args=args, logger=logger,
            )

        # -------------------------------------------------
        # Manifest
        # -------------------------------------------------

        manifest_path = (
            sheet_root
            / "manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        logger.success(
            "manifest written",
            path=str(
                manifest_path
            ),
        )
