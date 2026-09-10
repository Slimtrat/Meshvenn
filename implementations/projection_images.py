from __future__ import annotations

import math

from array import array
from dataclasses import dataclass
from typing import Any

import bpy

from ..core.image_mask import (
    BinaryMask,
    rgba_to_mask,
)
from ..core.native_bridge import (
    NativeProjection,
)
from ..core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..core.projected_material import (
    ProjectedMaterialView,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

IMPLEMENTATION_ID = (
    "projection-images"
)

MINIMUM_PROJECTION_COUNT = 2


# ---------------------------------------------------------
# Prepared view
# ---------------------------------------------------------

@dataclass(frozen=True)
class PreparedProjectionView:
    """
    One projection prepared for both geometry reconstruction
    and appearance generation.

    The INPUT implementation is the only layer which needs
    to understand Blender projection PropertyGroups.

    Downstream implementations consume this immutable
    representation instead.
    """

    name: str

    image_name: str

    width: int

    height: int

    azimuth_degrees: float

    elevation_degrees: float

    flip_x: bool

    weight: float

    mask: BinaryMask

    native_projection: NativeProjection

    material_view: ProjectedMaterialView

    @property
    def mask_pixels(
        self,
    ) -> int:
        return (
            self.mask
            .occupied_count
        )

    @property
    def empty_mask(
        self,
    ) -> bool:
        return (
            self.mask_pixels
            == 0
        )


# ---------------------------------------------------------
# INPUT stage output
# ---------------------------------------------------------

@dataclass(frozen=True)
class ProjectionImagesOutput:
    """
    Output contract of the built-in `projection-images`
    implementation.

    Geometry uses:

        native_projections

    Material uses:

        material_views

    Both therefore consume exactly the same prepared source
    set and cannot accidentally diverge in angles, masks or
    enabled-view filtering.
    """

    views: tuple[
        PreparedProjectionView,
        ...
    ]

    alpha_threshold: float

    enabled_projection_count: int

    missing_image_count: int

    @property
    def projection_count(
        self,
    ) -> int:
        return len(
            self.views
        )

    @property
    def native_projections(
        self,
    ) -> tuple[
        NativeProjection,
        ...
    ]:
        return tuple(
            view.native_projection
            for view
            in self.views
        )

    @property
    def material_views(
        self,
    ) -> tuple[
        ProjectedMaterialView,
        ...
    ]:
        return tuple(
            view.material_view
            for view
            in self.views
        )

    @property
    def view_names(
        self,
    ) -> tuple[
        str,
        ...
    ]:
        return tuple(
            view.name
            for view
            in self.views
        )

    @property
    def empty_mask_count(
        self,
    ) -> int:
        return sum(
            1
            for view
            in self.views
            if view.empty_mask
        )

    @property
    def total_mask_pixels(
        self,
    ) -> int:
        return sum(
            view.mask_pixels
            for view
            in self.views
        )


# ---------------------------------------------------------
# Context helpers
# ---------------------------------------------------------

def _resolve_settings(
    context: PipelineContext,
) -> Any:
    """
    Resolve BPT_PG_Settings without importing properties.py.

    Avoiding that dependency keeps the implementation layer
    from creating a properties <-> implementations import
    cycle.
    """

    if context.settings is not None:
        return (
            context.settings
        )

    scene = context.scene

    if scene is None:
        return None

    return getattr(
        scene,
        "bpt_settings",
        None,
    )


def require_projection_images_output(
    context: PipelineContext,
) -> ProjectionImagesOutput:
    """
    Typed accessor used by downstream built-in
    implementations.
    """

    output = (
        context.require_output(
            PipelineStage.INPUT
        )
    )

    if not isinstance(
        output,
        ProjectionImagesOutput,
    ):
        raise TypeError(
            (
                "INPUT output is incompatible with "
                '"projection-images". Expected '
                "ProjectionImagesOutput, received "
                f"{type(output).__name__}."
            )
        )

    return output


# ---------------------------------------------------------
# Blender image extraction
# ---------------------------------------------------------

def _image_pixels(
    image: bpy.types.Image,
) -> tuple[
    array,
    int,
    int,
]:
    """
    Copy one Blender image buffer efficiently.

    ProjectedMaterialView performs its own copy because it
    owns an independent ImageBuffer. The copy here exists for
    mask generation.

    This is still one INPUT preparation step, not repeated
    during geometry reconstruction.
    """

    image.update()

    width = int(
        image.size[0]
    )

    height = int(
        image.size[1]
    )

    if (
        width <= 0
        or height <= 0
    ):
        raise ValueError(
            (
                f'Image "{image.name}" has invalid '
                f"dimensions: {width}x{height}."
            )
        )

    expected_float_count = (
        width
        * height
        * 4
    )

    pixels = array(
        "f",
        [0.0],
    ) * expected_float_count

    image.pixels.foreach_get(
        pixels
    )

    if (
        len(pixels)
        != expected_float_count
    ):
        raise RuntimeError(
            (
                f'Image "{image.name}" returned '
                "an unexpected pixel buffer size."
            )
        )

    return (
        pixels,
        width,
        height,
    )


# ---------------------------------------------------------
# Projection preparation
# ---------------------------------------------------------

def _prepare_projection(
    projection,
    *,
    alpha_threshold: float,
) -> PreparedProjectionView:
    image = (
        projection.image
    )

    if image is None:
        raise ValueError(
            (
                f'Projection "{projection.name}" '
                "has no image."
            )
        )

    (
        pixels,
        width,
        height,
    ) = _image_pixels(
        image
    )

    mask = rgba_to_mask(
        pixels=pixels,
        width=width,
        height=height,
        alpha_threshold=(
            alpha_threshold
        ),
    )

    azimuth_degrees = (
        math.degrees(
            float(
                projection.azimuth
            )
        )
    )

    elevation_degrees = (
        math.degrees(
            float(
                projection.elevation
            )
        )
    )

    flip_x = bool(
        projection.flip_x
    )

    weight = max(
        0.0,
        float(
            projection.weight
        ),
    )

    name = str(
        projection.name
    ).strip()

    if not name:
        name = "Projection"

    # -----------------------------------------------------
    # Geometry representation
    #
    # IMPORTANT:
    #
    # An empty BinaryMask is deliberately retained.
    #
    # Mathematically, an enabled empty silhouette is a hard
    # visual-hull constraint:
    #
    #     silhouette = ∅
    #         ↓
    #     hull = ∅
    #
    # Silently dropping it would weaken the user's input.
    # -----------------------------------------------------

    native_projection = (
        NativeProjection(
            mask=mask,
            azimuth_degrees=(
                azimuth_degrees
            ),
            elevation_degrees=(
                elevation_degrees
            ),
            flip_x=(
                flip_x
            ),
        )
    )

    # -----------------------------------------------------
    # Appearance representation
    #
    # ProjectedMaterialView copies image pixels internally,
    # so the resulting INPUT output does not need to perform
    # repeated RNA pixel access later.
    # -----------------------------------------------------

    material_view = (
        ProjectedMaterialView
        .from_blender_image(
            name=name,
            image=image,
            azimuth_degrees=(
                azimuth_degrees
            ),
            elevation_degrees=(
                elevation_degrees
            ),
            flip_x=(
                flip_x
            ),
            weight=(
                weight
            ),
            mask=mask,
        )
    )

    return PreparedProjectionView(
        name=name,
        image_name=str(
            image.name
        ),
        width=width,
        height=height,
        azimuth_degrees=(
            azimuth_degrees
        ),
        elevation_degrees=(
            elevation_degrees
        ),
        flip_x=(
            flip_x
        ),
        weight=(
            weight
        ),
        mask=mask,
        native_projection=(
            native_projection
        ),
        material_view=(
            material_view
        ),
    )


# ---------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------

def _projection_counts(
    settings,
) -> tuple[
    int,
    int,
]:
    """
    Return:

        enabled projection count
        enabled projections with an image
    """

    enabled = 0
    ready = 0

    for projection in (
        settings.projections
    ):
        if not projection.enabled:
            continue

        enabled += 1

        if projection.image is not None:
            ready += 1

    return (
        enabled,
        ready,
    )


# ---------------------------------------------------------
# Implementation
# ---------------------------------------------------------

class ProjectionImagesImplementation:
    """
    Built-in INPUT implementation.

    Blender Projection PropertyGroups
            ↓
    BinaryMask
            +
    NativeProjection
            +
    ProjectedMaterialView
            ↓
    ProjectionImagesOutput
    """

    _descriptor = (
        ImplementationDescriptor(
            identifier=(
                IMPLEMENTATION_ID
            ),
            stage=(
                PipelineStage.INPUT
            ),
            label="Projection Images",
            description=(
                "Prepare enabled silhouette/RGBA views "
                "for geometry reconstruction and material "
                "projection."
            ),
            version="1",
            experimental=False,
            supports_headless=True,
            capabilities=(
                "projection-images",
                "silhouette-mask",
                "rgba-material-source",
                "arbitrary-view-angle",
                "view-weight",
            ),
        )
    )

    @property
    def descriptor(
        self,
    ) -> ImplementationDescriptor:
        return (
            self._descriptor
        )

    # -----------------------------------------------------
    # Availability
    # -----------------------------------------------------

    def availability(
        self,
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
                    "Meshvenn settings are unavailable."
                )
            )

        projections = getattr(
            settings,
            "projections",
            None,
        )

        if projections is None:
            return (
                ImplementationAvailability
                .unavailable(
                    "Projection settings are unavailable."
                )
            )

        (
            enabled_count,
            ready_count,
        ) = _projection_counts(
            settings
        )

        if (
            ready_count
            < MINIMUM_PROJECTION_COUNT
        ):
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "At least two enabled projections "
                        "with images are required."
                    ),
                    details={
                        "enabled_projections": (
                            enabled_count
                        ),
                        "ready_projections": (
                            ready_count
                        ),
                        "required_projections": (
                            MINIMUM_PROJECTION_COUNT
                        ),
                    },
                )
            )

        missing_count = (
            enabled_count
            - ready_count
        )

        if missing_count > 0:
            return (
                ImplementationAvailability
                .degraded(
                    (
                        f"{missing_count} enabled "
                        "projection"
                        + (
                            "s"
                            if missing_count != 1
                            else ""
                        )
                        + " have no image and will be "
                        "ignored."
                    ),
                    details={
                        "enabled_projections": (
                            enabled_count
                        ),
                        "ready_projections": (
                            ready_count
                        ),
                        "missing_images": (
                            missing_count
                        ),
                    },
                )
            )

        return (
            ImplementationAvailability
            .ready_state(
                details={
                    "enabled_projections": (
                        enabled_count
                    ),
                    "ready_projections": (
                        ready_count
                    ),
                }
            )
        )

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        settings = (
            _resolve_settings(
                context
            )
        )

        if settings is None:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.INPUT
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "Meshvenn settings are unavailable."
                    ),
                )
            )

        alpha_threshold = float(
            settings.alpha_threshold
        )

        if (
            not math.isfinite(
                alpha_threshold
            )
            or alpha_threshold < 0.0
            or alpha_threshold > 1.0
        ):
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.INPUT
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "Alpha threshold must be finite "
                        "and inside [0, 1]."
                    ),
                )
            )

        prepared_views: list[
            PreparedProjectionView
        ] = []

        enabled_projection_count = 0

        missing_image_count = 0

        missing_image_names: list[
            str
        ] = []

        # -------------------------------------------------
        # Build one immutable input bundle.
        # -------------------------------------------------

        for projection in (
            settings.projections
        ):
            if not projection.enabled:
                continue

            enabled_projection_count += 1

            if projection.image is None:
                missing_image_count += 1

                missing_image_names.append(
                    str(
                        projection.name
                    )
                )

                continue

            try:
                prepared = (
                    _prepare_projection(
                        projection,
                        alpha_threshold=(
                            alpha_threshold
                        ),
                    )
                )

            except Exception as exc:
                return (
                    StageExecutionResult
                    .failed_result(
                        stage=(
                            PipelineStage.INPUT
                        ),
                        implementation_id=(
                            IMPLEMENTATION_ID
                        ),
                        message=(
                            "Could not prepare projection "
                            f'"{projection.name}": {exc}'
                        ),
                        metadata={
                            "projection": str(
                                projection.name
                            ),
                            "exception_type": (
                                type(exc).__name__
                            ),
                        },
                    )
                )

            prepared_views.append(
                prepared
            )

        if (
            len(prepared_views)
            < MINIMUM_PROJECTION_COUNT
        ):
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.INPUT
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "At least two enabled projections "
                        "with images are required."
                    ),
                    metadata={
                        "enabled_projections": (
                            enabled_projection_count
                        ),
                        "prepared_projections": (
                            len(
                                prepared_views
                            )
                        ),
                        "missing_images": (
                            missing_image_count
                        ),
                    },
                )
            )

        output = (
            ProjectionImagesOutput(
                views=tuple(
                    prepared_views
                ),
                alpha_threshold=(
                    alpha_threshold
                ),
                enabled_projection_count=(
                    enabled_projection_count
                ),
                missing_image_count=(
                    missing_image_count
                ),
            )
        )

        empty_masks = [
            view.name
            for view
            in output.views
            if view.empty_mask
        ]

        # -------------------------------------------------
        # Expose lightweight run information independently
        # from the stage output.
        # -------------------------------------------------

        context.metadata[
            "projection_view_names"
        ] = list(
            output.view_names
        )

        context.metadata[
            "projection_count"
        ] = (
            output.projection_count
        )

        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    PipelineStage.INPUT
                ),
                implementation_id=(
                    IMPLEMENTATION_ID
                ),
                payload=output,
                message=(
                    f"Prepared "
                    f"{output.projection_count} "
                    "projection views."
                ),
                metrics={
                    "enabled_projections": (
                        enabled_projection_count
                    ),
                    "prepared_projections": (
                        output.projection_count
                    ),
                    "missing_images": (
                        missing_image_count
                    ),
                    "empty_masks": (
                        output.empty_mask_count
                    ),
                    "mask_pixels": (
                        output.total_mask_pixels
                    ),
                },
                metadata={
                    "views": [
                        {
                            "name": (
                                view.name
                            ),
                            "image": (
                                view.image_name
                            ),
                            "width": (
                                view.width
                            ),
                            "height": (
                                view.height
                            ),
                            "azimuth_degrees": (
                                view
                                .azimuth_degrees
                            ),
                            "elevation_degrees": (
                                view
                                .elevation_degrees
                            ),
                            "flip_x": (
                                view.flip_x
                            ),
                            "weight": (
                                view.weight
                            ),
                            "mask_pixels": (
                                view.mask_pixels
                            ),
                            "empty_mask": (
                                view.empty_mask
                            ),
                        }
                        for view
                        in output.views
                    ],
                    "missing_image_views": (
                        missing_image_names
                    ),
                    "empty_mask_views": (
                        empty_masks
                    ),
                    "alpha_threshold": (
                        alpha_threshold
                    ),
                },
            )
        )