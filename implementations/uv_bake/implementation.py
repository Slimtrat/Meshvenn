from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

import bpy

from ...core.geometry_contracts import (
    GeometrySurfaceOutput,
    require_geometry_surface_output,
)
from ...core.material_blend import (
    MaterialBlendConfig,
)
from ...core.material_visibility import (
    MeshVisibilityTester,
)
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.projected_material import (
    DEFAULT_FALLBACK_COLOR,
    blend_projected_color,
)
from ...core.uv_bake import (
    SurfaceColorSample,
    UVBakeConfig,
    UVBakeResult,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
)

from . import constants as _dependency_0
from . import config as _dependency_1
from . import diagnostics as _dependency_2
from . import settings as _dependency_3
from . import geometry as _dependency_4
from . import triangles as _dependency_5
from . import sampler as _dependency_6
from . import assets as _dependency_7
from . import metadata as _dependency_8
from . import ui as _dependency_9
for _dependency in (_dependency_0, _dependency_1, _dependency_2, _dependency_3, _dependency_4, _dependency_5, _dependency_6, _dependency_7, _dependency_8, _dependency_9,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

class UVBakeImplementation:
    """
    Built-in MATERIAL implementation.

        GeometrySurfaceOutput
                ↓
        source.material_views
                ↓
        GeometryProjectionSpace
                ↓
        Smart UV unwrap
                ↓
        UV-space rasterization
                ↓
        Projected Color V1.2 sampler
                ↓
        baked image texture
                ↓
        Principled material

    UV Bake does not depend on the concrete GEOMETRY
    implementation.

    Native Visual Hull and SDF Reconstruction can therefore
    use the exact same material pipeline.
    """

    _descriptor = (
        ImplementationDescriptor(
            identifier=(
                IMPLEMENTATION_ID
            ),

            stage=(
                PipelineStage.MATERIAL
            ),

            label=(
                "UV Bake V2"
            ),

            description=(
                "Bake visibility-aware multi-view "
                "projected color into a portable UV "
                "texture."
            ),

            version="2",

            experimental=True,

            supports_headless=True,

            capabilities=(
                "uv-texture",
                "smart-unwrap",
                "multi-view",
                "visibility-raycast",
                "adaptive-blend",
                "texture-padding",
                "portable-material",
                "generic-geometry",
                "projection-space",
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

        try:
            geometry = (
                require_geometry_surface_output(
                    context
                )
            )

        except Exception as exc:
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "Compatible GEOMETRY surface "
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
            _validate_geometry(
                geometry
            )

            material_views = (
                _material_views_from_geometry(
                    geometry
                )
            )

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
                        "UV Bake V2 is not "
                        f"available: {exc}"
                    ),
                    details={
                        "geometry_implementation": (
                            geometry
                            .implementation_id
                        ),
                    },
                )
            )

        mesh = (
            geometry
            .blender_object
            .data
        )

        if (
            config.reuse_existing_uv
            and mesh.uv_layers.active
            is None
        ):
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "Reuse Existing UV is enabled "
                        "but the mesh has no UV map."
                    ),
                    details={
                        "geometry_implementation": (
                            geometry
                            .implementation_id
                        ),
                    },
                )
            )

        projection_space = (
            geometry
            .projection_space
        )

        return (
            ImplementationAvailability
            .ready_state(
                details={
                    "object": (
                        geometry
                        .object_name
                    ),

                    "geometry_implementation": (
                        geometry
                        .implementation_id
                    ),

                    "views": len(
                        material_views
                    ),

                    "texture_size": (
                        config
                        .texture_size
                    ),

                    "padding_pixels": (
                        config
                        .padding_pixels
                    ),

                    "samples_per_axis": (
                        config
                        .samples_per_axis
                    ),

                    "reuse_existing_uv": (
                        config
                        .reuse_existing_uv
                    ),

                    "requested_island_margin": (
                        config
                        .island_margin
                    ),

                    "effective_island_margin": (
                        config
                        .effective_island_margin_fraction
                    ),

                    "effective_island_margin_pixels": (
                        config
                        .effective_island_margin_pixels
                    ),

                    "projection_space": {
                        "width": (
                            projection_space
                            .width
                        ),

                        "depth": (
                            projection_space
                            .depth
                        ),

                        "height": (
                            projection_space
                            .height
                        ),

                        "voxel_size": (
                            projection_space
                            .voxel_size
                        ),

                        "center_xy": (
                            projection_space
                            .center_xy
                        ),

                        "convention": (
                            projection_space
                            .convention
                            .value
                        ),
                    },
                }
            )
        )

    # -----------------------------------------------------
    # Generic UI hook
    # -----------------------------------------------------

    def draw_settings(
        self,
        layout,
        context,
    ) -> None:
        settings = getattr(
            context.scene,
            "bpt_settings",
            None,
        )

        if settings is None:
            return

        texture_box = (
            layout.box()
        )

        texture_box.label(
            text="Texture",
            icon="TEXTURE",
        )

        if not _draw_optional_property(
            texture_box,
            settings,
            "uv_bake_texture_size",
            "Texture Size",
        ):
            texture_box.label(
                text=(
                    "Texture Size: "
                    f"{DEFAULT_TEXTURE_SIZE}"
                )
            )

        if not _draw_optional_property(
            texture_box,
            settings,
            "uv_bake_padding_pixels",
            "Padding",
        ):
            texture_box.label(
                text=(
                    "Padding: "
                    f"{DEFAULT_PADDING_PIXELS}px"
                )
            )

        if not _draw_optional_property(
            texture_box,
            settings,
            "uv_bake_samples_per_axis",
            "Samples",
        ):
            texture_box.label(
                text=(
                    "Samples: "
                    f"{DEFAULT_SAMPLES_PER_AXIS}"
                    "×"
                    f"{DEFAULT_SAMPLES_PER_AXIS}"
                )
            )

        uv_box = (
            layout.box()
        )

        uv_box.label(
            text="UV Mapping",
            icon="UV",
        )

        if not _draw_optional_property(
            uv_box,
            settings,
            "uv_bake_reuse_existing_uv",
            "Reuse Existing UV",
        ):
            uv_box.label(
                text="Smart UV Project"
            )

        _draw_optional_property(
            uv_box,
            settings,
            "uv_bake_island_margin",
            "Maximum Island Margin",
        )

        _draw_optional_property(
            uv_box,
            settings,
            "uv_bake_angle_limit_degrees",
            "Angle Limit",
        )

        try:
            config = (
                _config_from_settings(
                    settings
                )
            )

            if not (
                config
                .reuse_existing_uv
            ):
                uv_box.label(
                    text=(
                        "Effective Margin: "
                        f"{config.effective_island_margin_pixels:.2f}px "
                        "("
                        f"{config.effective_island_margin_fraction:.6f}"
                        ")"
                    ),
                    icon="INFO",
                )

        except Exception:
            pass

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------


    def execute(self, context: PipelineContext) -> StageExecutionResult:
        from .execution import execute_uv_bake
        return execute_uv_bake(self, context)
