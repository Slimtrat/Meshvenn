from __future__ import annotations

from .shared import ExtractedView, NativeProjection, ProjectedMaterialView, RunLogger, bpy

def prepare_projections(
    views: list[
        ExtractedView
    ],
    *,
    logger: RunLogger,
) -> dict[
    str,
    NativeProjection,
]:
    valid_views = [
        view
        for view in views
        if (
            view.valid
            and view.mask.occupied_count > 0
        )
    ]

    projections: dict[
        str,
        NativeProjection,
    ] = {}

    for index, view in enumerate(
        valid_views,
        start=1,
    ):
        logger.progress(
            index,
            len(
                valid_views
            ),
            f"mask {view.name}",
        )

        projections[
            view.name
        ] = NativeProjection(
            mask=view.mask,
            azimuth_degrees=(
                view.azimuth_degrees
            ),
            elevation_degrees=(
                view.elevation_degrees
            ),
            flip_x=False,
        )

    return projections

def prepare_material_views(
    views: list[
        ExtractedView
    ],
    *,
    logger: RunLogger,
) -> dict[
    str,
    ProjectedMaterialView,
]:
    """
    Load the cleaned RGBA projection PNGs and convert
    them into in-memory ProjectedMaterialView instances.

    ProjectedMaterialView copies the image pixels, so the
    temporary Blender Image can immediately be released.
    """

    valid_views = [
        view
        for view in views
        if (
            view.valid
            and view.mask.occupied_count > 0
        )
    ]

    material_views: dict[
        str,
        ProjectedMaterialView,
    ] = {}

    for index, view in enumerate(
        valid_views,
        start=1,
    ):
        logger.progress(
            index,
            len(
                valid_views
            ),
            f"RGB {view.name}",
        )

        image = bpy.data.images.load(
            str(
                view.path.resolve()
            ),
            check_existing=False,
        )

        try:
            material_views[
                view.name
            ] = (
                ProjectedMaterialView
                .from_blender_image(
                    name=view.name,
                    image=image,
                    azimuth_degrees=(
                        view
                        .azimuth_degrees
                    ),
                    elevation_degrees=(
                        view
                        .elevation_degrees
                    ),
                    flip_x=False,
                    weight=1.0,
                    mask=view.mask,
                )
            )

        finally:
            bpy.data.images.remove(
                image
            )

    return material_views

def material_views_for_snapshot(
    material_views: dict[
        str,
        ProjectedMaterialView,
    ],
    applied_views: tuple[
        str,
        ...
    ]
    | list[
        str
    ],
) -> list[
    ProjectedMaterialView
]:
    """
    Preserve the reconstruction view order and ensure
    each profile only receives images which participated
    in that profile's visual-hull reconstruction.
    """

    result: list[
        ProjectedMaterialView
    ] = []

    for view_name in applied_views:
        view = material_views.get(
            view_name
        )

        if view is None:
            continue

        result.append(
            view
        )

    return result

def material_visibility_manifest(
    obj: bpy.types.Object,
) -> dict:
    """
    Extract visibility metadata written by
    apply_projected_material().
    """

    enabled = bool(
        obj.get(
            "bpt_material_visibility",
            False,
        )
    )

    epsilon = obj.get(
        "bpt_material_visibility_epsilon"
    )

    max_distance = obj.get(
        "bpt_material_visibility_max_distance"
    )

    return {
        "enabled": enabled,
        "mode": str(
            obj.get(
                "bpt_material_visibility_mode",
                "disabled",
            )
        ),
        "epsilon": (
            float(
                epsilon
            )
            if epsilon is not None
            else None
        ),
        "max_distance": (
            float(
                max_distance
            )
            if max_distance is not None
            else None
        ),
    }

def material_blend_manifest(
    obj: bpy.types.Object,
) -> dict:
    """
    Extract the effective V1.2 blend configuration written
    by apply_projected_material().

    The object metadata is the source of truth here. This
    ensures generated manifests report the configuration
    actually used for projection rather than duplicating
    default values in this script.
    """

    min_facing = obj.get(
        "bpt_material_blend_min_facing"
    )

    facing_power = obj.get(
        "bpt_material_blend_facing_power"
    )

    relative_score_cutoff = obj.get(
        "bpt_material_blend_relative_score_cutoff"
    )

    max_contributors = obj.get(
        "bpt_material_blend_max_contributors"
    )

    weight_power = obj.get(
        "bpt_material_blend_weight_power"
    )

    return {
        "mode": str(
            obj.get(
                "bpt_material_blend_mode",
                "disabled",
            )
        ),
        "min_facing": (
            float(
                min_facing
            )
            if min_facing is not None
            else None
        ),
        "facing_power": (
            float(
                facing_power
            )
            if facing_power is not None
            else None
        ),
        "relative_score_cutoff": (
            float(
                relative_score_cutoff
            )
            if relative_score_cutoff is not None
            else None
        ),
        "max_contributors": (
            int(
                max_contributors
            )
            if max_contributors is not None
            else None
        ),
        "weight_power": (
            float(
                weight_power
            )
            if weight_power is not None
            else None
        ),
    }

def material_stats_manifest(
    material_stats,
) -> dict:
    """
    Serialize MaterialProjectionStats without making the
    JSON generator dependent on dataclasses.asdict().

    Keeping this explicit makes the manifest schema visible
    and deliberate.
    """

    return {
        "vertex_count": (
            material_stats
            .vertex_count
        ),
        "loop_count": (
            material_stats
            .loop_count
        ),
        "view_count": (
            material_stats
            .view_count
        ),
        "projected_vertices": (
            material_stats
            .projected_vertices
        ),
        "fallback_vertices": (
            material_stats
            .fallback_vertices
        ),
        "projected_fallback_vertices": (
            material_stats
            .projected_fallback_vertices
        ),
        "neutral_fallback_vertices": (
            material_stats
            .neutral_fallback_vertices
        ),
        "accepted_samples": (
            material_stats
            .accepted_samples
        ),
        "rejected_samples": (
            material_stats
            .rejected_samples
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
    }
