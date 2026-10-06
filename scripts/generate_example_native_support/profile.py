from __future__ import annotations

from .shared import BLEND_MODE, MATERIAL_MODE, Path, RunLogger, VISIBILITY_MODE, argparse
from .profile_reporting import _finalize_profile, _log_material
from .profile_setup import _create_mesh_and_material, _initial_profile_info
from dataclasses import replace
from core.surface_refinement import refine_native_surface
from core.contour_surface import ContourSurface
from core.geometry_contracts import GeometryProjectionSpace

def _process_profile(
    *,
    sheet_name: str,
    level_name: str,
    snapshot,
    material_views: dict,
    manifest: dict,
    scans_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
    projections: dict,
    contour_cache: dict,
) -> None:
    level_logger = (
        logger.child()
    )
    refinement = {"mode": "none", "applied": False}
    if snapshot.mesh is not None:
        contour = None
        if getattr(args, "surface_refinement", "none") == "organic":
            active_views = [projections[name] for name in snapshot.applied_views]
            contour = ContourSurface.from_views(active_views, GeometryProjectionSpace(
                snapshot.volume.width, snapshot.volume.depth, snapshot.volume.height,
                voxel_size=args.voxel_size, center_xy=True,
            ), cache=contour_cache)
        mesh, refinement = refine_native_surface(
            snapshot.mesh, voxel_size=args.voxel_size,
            mode=getattr(args, "surface_refinement", "none"), mesh_mode=args.mesh_mode,
            contour_surface=contour,
        )
        snapshot = replace(snapshot, mesh=mesh)

    with level_logger.section(
        level_name,
        occupied_voxels=(
            snapshot
            .volume
            .occupied_count
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
    ):
        active_material_views, profile_info = _initial_profile_info(
            snapshot, material_views, args
        )
        profile_info["surface_refinement"] = refinement
        if snapshot.mesh is None:
            manifest["profiles"][level_name] = profile_info
            return
        obj, material_stats, visibility_info, blend_info, stats_info = (
            _create_mesh_and_material(
                snapshot=snapshot, sheet_name=sheet_name,
                level_name=level_name, active_material_views=active_material_views,
                args=args, level_logger=level_logger,
            )
        )
        _log_material(
            level_logger=level_logger, material_stats=material_stats,
            active_material_views=active_material_views,
            visibility_info=visibility_info, blend_info=blend_info,
        )
        _finalize_profile(
            obj=obj, snapshot=snapshot, sheet_name=sheet_name,
            level_name=level_name, scans_root=scans_root, args=args,
            level_logger=level_logger, active_material_views=active_material_views,
            profile_info=profile_info, material_stats=material_stats,
            visibility_info=visibility_info, blend_info=blend_info,
            stats_info=stats_info,
        )
        manifest["profiles"][level_name] = profile_info
