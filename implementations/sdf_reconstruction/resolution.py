from __future__ import annotations

from typing import Any

from ...core.image_mask import BinaryMask
from ...core.pipeline_contracts import PipelineContext, PipelineStage
from ...core.sdf import DEFAULT_ISO_LEVEL, DEFAULT_REFERENCE_MAX_VOXELS, DEFAULT_SMOOTHNESS, DEFAULT_SURFACE_OFFSET
from ...core.sdf_surface import DEFAULT_GRADIENT_STEP_SCALE
from .config import DEFAULT_CENTER_XY, DEFAULT_NORMALIZE_HEIGHT, DEFAULT_RESOLUTION, DEFAULT_TARGET_HEIGHT, DEFAULT_VOXEL_SIZE, IMPLEMENTATION_ID, MINIMUM_PROJECTION_COUNT, SDFReconstructionConfig
from .output import SDFReconstructionOutput

# =========================================================
# Context / source
# =========================================================

def _resolve_settings(
    context: PipelineContext,
) -> Any:
    if context.settings is not None:
        return (
            context.settings
        )

    if context.scene is None:
        return None

    return getattr(
        context.scene,
        "bpt_settings",
        None,
    )


def _require_input_source(
    context: PipelineContext,
) -> Any:
    """
    SDF uses capabilities instead of depending on the
    concrete ProjectionImagesOutput class.

    Required source capability:

        source.views

    Required view capabilities:

        mask
        azimuth_degrees
        elevation_degrees

    Optional:

        flip_x
        name
    """

    source = (
        context.require_output(
            PipelineStage.INPUT
        )
    )

    views = getattr(
        source,
        "views",
        None,
    )

    if views is None:
        raise TypeError(
            (
                "INPUT output does not expose "
                "projection views required "
                "by SDF Reconstruction."
            )
        )

    return source


def _source_views(
    source: Any,
) -> tuple[
    Any,
    ...
]:
    views = getattr(
        source,
        "views",
        None,
    )

    if views is None:
        raise TypeError(
            (
                "INPUT source does not "
                "expose views."
            )
        )

    try:
        resolved = tuple(
            views
        )

    except TypeError as exc:
        raise TypeError(
            (
                "INPUT source views "
                "are not iterable."
            )
        ) from exc

    if len(
        resolved
    ) < MINIMUM_PROJECTION_COUNT:
        raise ValueError(
            (
                "SDF Reconstruction requires "
                "at least two projection views."
            )
        )

    for (
        index,
        view,
    ) in enumerate(
        resolved
    ):
        mask = getattr(
            view,
            "mask",
            None,
        )

        if not isinstance(
            mask,
            BinaryMask,
        ):
            raise TypeError(
                (
                    f"Projection {index} does not "
                    "expose a BinaryMask."
                )
            )

        try:
            float(
                getattr(
                    view,
                    "azimuth_degrees",
                )
            )

            float(
                getattr(
                    view,
                    "elevation_degrees",
                )
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            raise TypeError(
                (
                    f"Projection {index} does not "
                    "expose valid camera angles."
                )
            ) from exc

    return resolved


def require_sdf_reconstruction_output(
    context: PipelineContext,
) -> SDFReconstructionOutput:
    output = (
        context.require_output(
            PipelineStage.GEOMETRY
        )
    )

    if not isinstance(
        output,
        SDFReconstructionOutput,
    ):
        raise TypeError(
            (
                "GEOMETRY output is incompatible "
                f'with "{IMPLEMENTATION_ID}". '
                "Expected SDFReconstructionOutput, "
                "received "
                f"{type(output).__name__}."
            )
        )

    return output


# =========================================================
# Settings resolution
# =========================================================

def _read_setting(
    settings: Any,
    name: str,
    default: Any,
) -> Any:
    if settings is None:
        return default

    return getattr(
        settings,
        name,
        default,
    )


def _legacy_geometry_setting(
    settings: Any,
    sdf_name: str,
    legacy_name: str,
    default: Any,
) -> Any:
    """
    Prefer the future SDF-specific property.

    Fall back to the existing Visual Hull geometry property
    so SDF V1 is immediately runnable before dedicated UI
    controls land.
    """

    if settings is None:
        return default

    if hasattr(
        settings,
        sdf_name,
    ):
        return getattr(
            settings,
            sdf_name,
        )

    return getattr(
        settings,
        legacy_name,
        default,
    )


def _config_from_settings(
    settings: Any,
) -> SDFReconstructionConfig:
    config = (
        SDFReconstructionConfig(
            resolution=int(
                _legacy_geometry_setting(
                    settings,
                    "sdf_resolution",
                    "resolution",
                    DEFAULT_RESOLUTION,
                )
            ),

            symmetry_x=bool(
                _legacy_geometry_setting(
                    settings,
                    "sdf_symmetry_x",
                    "symmetry_x",
                    False,
                )
            ),

            voxel_size=float(
                _legacy_geometry_setting(
                    settings,
                    "sdf_voxel_size",
                    "voxel_size",
                    DEFAULT_VOXEL_SIZE,
                )
            ),

            center_xy=bool(
                _read_setting(
                    settings,
                    "sdf_center_xy",
                    DEFAULT_CENTER_XY,
                )
            ),

            smoothness=float(
                _read_setting(
                    settings,
                    "sdf_smoothness",
                    DEFAULT_SMOOTHNESS,
                )
            ),

            surface_offset=float(
                _read_setting(
                    settings,
                    "sdf_surface_offset",
                    DEFAULT_SURFACE_OFFSET,
                )
            ),

            iso_level=float(
                _read_setting(
                    settings,
                    "sdf_iso_level",
                    DEFAULT_ISO_LEVEL,
                )
            ),

            gradient_step_scale=float(
                _read_setting(
                    settings,
                    "sdf_gradient_step_scale",
                    DEFAULT_GRADIENT_STEP_SCALE,
                )
            ),

            normalize_height=bool(
                _read_setting(
                    settings,
                    "normalize_height",
                    DEFAULT_NORMALIZE_HEIGHT,
                )
            ),

            target_height=float(
                _read_setting(
                    settings,
                    "target_height",
                    DEFAULT_TARGET_HEIGHT,
                )
            ),

            max_reference_voxels=(
                DEFAULT_REFERENCE_MAX_VOXELS
            ),
        )
    )

    config.validate()

    return config
