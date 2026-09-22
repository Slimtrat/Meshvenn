from __future__ import annotations

from ...core.pipeline_contracts import ImplementationAvailability, PipelineContext
from .resolution import _config_from_settings, _require_input_source, _resolve_settings, _source_views


def get_sdf_availability(
    context: PipelineContext,
) -> ImplementationAvailability:
    settings = (
        _resolve_settings(
            context
        )
    )

    if settings is None:
        return (
            ImplementationAvailability
            .unavailable(
                (
                    "Meshvenn settings "
                    "are unavailable."
                )
            )
        )

    try:
        source = (
            _require_input_source(
                context
            )
        )

        views = (
            _source_views(
                source
            )
        )

    except Exception as exc:
        return (
            ImplementationAvailability
            .unavailable(
                (
                    "Prepared silhouette input "
                    "is unavailable."
                ),
                details={
                    "error": str(
                        exc
                    ),
                },
            )
        )

    try:
        config = (
            _config_from_settings(
                settings
            )
        )

    except Exception as exc:
        return (
            ImplementationAvailability
            .unavailable(
                (
                    "SDF Reconstruction "
                    "configuration is invalid."
                ),
                details={
                    "error": str(
                        exc
                    ),
                },
            )
        )

    empty_mask_count = sum(
        1
        for view
        in views
        if (
            view.mask
            .occupied_count
            == 0
        )
    )

    details = {
        "backend": (
            "python-reference"
        ),

        "projection_count": len(
            views
        ),

        "resolution": (
            config.resolution
        ),

        "sample_count": (
            config.sample_count
        ),

        "estimated_field_mib": (
            config
            .estimated_field_mib
        ),

        "symmetry_x": (
            config.symmetry_x
        ),

        "smoothness": (
            config.smoothness
        ),

        "surface_offset": (
            config.surface_offset
        ),

        "iso_level": (
            config.iso_level
        ),

        "empty_masks": (
            empty_mask_count
        ),
    }

    reasons = [
        (
            "SDF V1 currently uses the "
            "pure-Python reference backend; "
            "native acceleration is pending."
        )
    ]

    if empty_mask_count > 0:
        reasons.append(
            (
                f"{empty_mask_count} projection "
                "mask"
                + (
                    "s are"
                    if empty_mask_count != 1
                    else " is"
                )
                + " empty; the mathematical "
                "intersection may be empty."
            )
        )

    return (
        ImplementationAvailability
        .degraded(
            " ".join(
                reasons
            ),
            details=details,
        )
    )

# -----------------------------------------------------
# Settings UI
# -----------------------------------------------------
