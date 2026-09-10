from __future__ import annotations

import math

from dataclasses import (
    dataclass,
    field,
)
from enum import Enum
from typing import (
    Any,
    Mapping,
)

from .pipeline_contracts import (
    PipelineContext,
    PipelineStage,
    validate_implementation_id,
)


# =========================================================
# Coordinate convention
# =========================================================

class GeometryProjectionConvention(
    str,
    Enum,
):
    """
    Coordinate convention used by a GEOMETRY output when
    downstream stages need to project surface positions back
    into the source images.

    SURFACE_ENVELOPE_V1 matches Meshvenn's current native
    projection convention:

        X
            0 .. width * voxel_size

            or, when center_xy=True:

            -width * voxel_size / 2
            ..
            +width * voxel_size / 2

        Y
            same convention using depth

        Z
            0 .. height * voxel_size

    Projection normalization maps the complete surface
    envelope to:

        [-1, +1]

    rather than interpreting surface vertices as voxel
    centres.

    This is the convention already used by
    core/projection_math.py.
    """

    SURFACE_ENVELOPE_V1 = (
        "surface-envelope-v1"
    )


DEFAULT_PROJECTION_CONVENTION = (
    GeometryProjectionConvention
    .SURFACE_ENVELOPE_V1
)


# =========================================================
# Projection space
# =========================================================

@dataclass(frozen=True)
class GeometryProjectionSpace:
    """
    Reconstruction coordinate system shared between
    GEOMETRY and projection-dependent downstream stages.

    This deliberately contains no Blender-specific or
    algorithm-specific state.

    A MATERIAL implementation should need this:

        projection_space.width
        projection_space.depth
        projection_space.height
        projection_space.voxel_size
        projection_space.center_xy

    and should NOT need:

        NativeVolume
        NativeMesh
        SDFVolume
        VisualHullOutput
        implementation internals

    The mesh-local surface coordinates exposed by the
    GeometrySurfaceOutput MUST remain expressed in this
    projection space until every projection-dependent stage
    has completed.
    """

    width: int

    depth: int

    height: int

    voxel_size: float = 1.0

    center_xy: bool = True

    convention: GeometryProjectionConvention = (
        DEFAULT_PROJECTION_CONVENTION
    )

    def __post_init__(
        self,
    ) -> None:
        # -------------------------------------------------
        # Dimensions
        # -------------------------------------------------

        for (
            name,
            value,
        ) in (
            (
                "width",
                self.width,
            ),
            (
                "depth",
                self.depth,
            ),
            (
                "height",
                self.height,
            ),
        ):
            if (
                not isinstance(
                    value,
                    int,
                )
                or isinstance(
                    value,
                    bool,
                )
                or value <= 0
            ):
                raise ValueError(
                    (
                        f"{name} must be a "
                        "positive integer."
                    )
                )

        # -------------------------------------------------
        # Voxel / grid spacing
        # -------------------------------------------------

        voxel_size = float(
            self.voxel_size
        )

        if (
            not math.isfinite(
                voxel_size
            )
            or voxel_size <= 0.0
        ):
            raise ValueError(
                (
                    "voxel_size must be "
                    "finite and greater "
                    "than zero."
                )
            )

        object.__setattr__(
            self,
            "voxel_size",
            voxel_size,
        )

        # -------------------------------------------------
        # Coordinate convention
        # -------------------------------------------------

        object.__setattr__(
            self,
            "center_xy",
            bool(
                self.center_xy
            ),
        )

        object.__setattr__(
            self,
            "convention",
            GeometryProjectionConvention(
                self.convention
            ),
        )

    # -----------------------------------------------------
    # Grid dimensions
    # -----------------------------------------------------

    @property
    def dimensions(
        self,
    ) -> tuple[
        int,
        int,
        int,
    ]:
        return (
            self.width,
            self.depth,
            self.height,
        )

    @property
    def voxel_count(
        self,
    ) -> int:
        return (
            self.width
            * self.depth
            * self.height
        )

    # -----------------------------------------------------
    # Physical dimensions
    # -----------------------------------------------------

    @property
    def physical_width(
        self,
    ) -> float:
        return (
            float(
                self.width
            )
            * self.voxel_size
        )

    @property
    def physical_depth(
        self,
    ) -> float:
        return (
            float(
                self.depth
            )
            * self.voxel_size
        )

    @property
    def physical_height(
        self,
    ) -> float:
        return (
            float(
                self.height
            )
            * self.voxel_size
        )

    @property
    def physical_dimensions(
        self,
    ) -> tuple[
        float,
        float,
        float,
    ]:
        return (
            self.physical_width,
            self.physical_depth,
            self.physical_height,
        )

    # -----------------------------------------------------
    # Local-space bounds
    # -----------------------------------------------------

    @property
    def minimum_local_point(
        self,
    ) -> tuple[
        float,
        float,
        float,
    ]:
        if self.center_xy:
            return (
                -self.physical_width
                * 0.5,

                -self.physical_depth
                * 0.5,

                0.0,
            )

        return (
            0.0,
            0.0,
            0.0,
        )

    @property
    def maximum_local_point(
        self,
    ) -> tuple[
        float,
        float,
        float,
    ]:
        if self.center_xy:
            return (
                self.physical_width
                * 0.5,

                self.physical_depth
                * 0.5,

                self.physical_height,
            )

        return (
            self.physical_width,
            self.physical_depth,
            self.physical_height,
        )

    @property
    def local_bounds(
        self,
    ) -> tuple[
        tuple[
            float,
            float,
            float,
        ],
        tuple[
            float,
            float,
            float,
        ],
    ]:
        return (
            self.minimum_local_point,
            self.maximum_local_point,
        )

    # -----------------------------------------------------
    # Projection helper
    # -----------------------------------------------------

    def as_projection_kwargs(
        self,
    ) -> dict[
        str,
        Any,
    ]:
        """
        Arguments currently consumed by Meshvenn's
        projection functions.

        Typical downstream usage:

            blend_projected_color(
                position,
                normal,
                views,
                **geometry.projection_space
                    .as_projection_kwargs(),
                ...
            )

        This keeps MATERIAL independent from the concrete
        GEOMETRY implementation.
        """

        if (
            self.convention
            != GeometryProjectionConvention
            .SURFACE_ENVELOPE_V1
        ):
            raise ValueError(
                (
                    "Projection convention is "
                    "not supported by the "
                    "current Meshvenn "
                    "projection engine: "
                    f"{self.convention.value}"
                )
            )

        return {
            "width": (
                self.width
            ),

            "depth": (
                self.depth
            ),

            "height": (
                self.height
            ),

            "voxel_size": (
                self.voxel_size
            ),

            "center_xy": (
                self.center_xy
            ),
        }


# =========================================================
# Mapping normalization
# =========================================================

def _normalize_mapping(
    value: (
        Mapping[
            str,
            Any,
        ]
        | None
    ),
    *,
    name: str,
) -> dict[
    str,
    Any,
]:
    """
    Normalize flexible implementation metrics/metadata.

    Values remain intentionally unrestricted because they
    may contain implementation-specific diagnostics.

    Keys must however remain stable strings so manifests and
    debug tooling can consume them consistently.
    """

    if value is None:
        return {}

    if not isinstance(
        value,
        Mapping,
    ):
        raise TypeError(
            (
                f"{name} must be "
                "a mapping."
            )
        )

    result: dict[
        str,
        Any,
    ] = {}

    for (
        key,
        item,
    ) in value.items():
        normalized_key = str(
            key
        ).strip()

        if not normalized_key:
            raise ValueError(
                (
                    f"{name} cannot "
                    "contain an empty key."
                )
            )

        result[
            normalized_key
        ] = item

    return result


# =========================================================
# Generic GEOMETRY output
# =========================================================

@dataclass(frozen=True)
class GeometrySurfaceOutput:
    """
    Generic contract returned by a Meshvenn GEOMETRY stage.

    Concrete geometry implementations may subclass this
    object and expose additional implementation-specific
    fields.

    Examples:

        NativeVisualHullOutput(
            ...
        )

        SDFReconstructionOutput(
            ...
        )

    Downstream stages should depend only on this base
    contract whenever possible.

    In particular MATERIAL, RIG and EXPORT should not need
    to know whether the geometry came from:

        visual hull
        SDF
        neural reconstruction
        imported mesh
        another future engine

    -------------------------------------------------------
    blender_object
    -------------------------------------------------------

    The surface object produced by GEOMETRY.

    The type is deliberately Any so this core module remains
    importable without bpy.

    Blender implementations will normally provide:

        bpy.types.Object

    Pure Python tests may provide a lightweight fake object.

    -------------------------------------------------------
    source
    -------------------------------------------------------

    INPUT-stage data from which this geometry was produced.

    The generic geometry contract intentionally does not
    require ProjectionImagesOutput specifically.

    Future INPUT implementations may provide other source
    types.

    -------------------------------------------------------
    projection_space
    -------------------------------------------------------

    Coordinate system required to project mesh-local surface
    positions back into the original views.

    This is the critical bridge between interchangeable
    GEOMETRY and MATERIAL implementations.

    -------------------------------------------------------
    implementation_id
    -------------------------------------------------------

    Stable implementation identifier, for example:

        native-visual-hull
        sdf-reconstruction-v1

    -------------------------------------------------------
    metrics / metadata
    -------------------------------------------------------

    Generic extension points for diagnostics.

    metrics:
        primarily numeric execution/output measurements.

    metadata:
        descriptive implementation information.

    These mappings must never be required by downstream
    algorithms for fundamental coordinate reconstruction.
    Fundamental geometry state belongs in explicit fields.
    """

    blender_object: Any

    source: Any

    projection_space: GeometryProjectionSpace

    implementation_id: str

    metrics: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    metadata: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    def __post_init__(
        self,
    ) -> None:
        if (
            self.blender_object
            is None
        ):
            raise ValueError(
                (
                    "GeometrySurfaceOutput "
                    "requires a surface object."
                )
            )

        if self.source is None:
            raise ValueError(
                (
                    "GeometrySurfaceOutput "
                    "requires its INPUT "
                    "source."
                )
            )

        if not isinstance(
            self.projection_space,
            GeometryProjectionSpace,
        ):
            raise TypeError(
                (
                    "projection_space must "
                    "be a "
                    "GeometryProjectionSpace."
                )
            )

        implementation_id = (
            validate_implementation_id(
                self.implementation_id
            )
        )

        object.__setattr__(
            self,
            "implementation_id",
            implementation_id,
        )

        object.__setattr__(
            self,
            "metrics",
            _normalize_mapping(
                self.metrics,
                name="metrics",
            ),
        )

        object.__setattr__(
            self,
            "metadata",
            _normalize_mapping(
                self.metadata,
                name="metadata",
            ),
        )

    # -----------------------------------------------------
    # Projection-space compatibility properties
    #
    # These properties make migration easy for existing
    # code while keeping the real source of truth grouped
    # inside projection_space.
    # -----------------------------------------------------

    @property
    def width(
        self,
    ) -> int:
        return (
            self.projection_space
            .width
        )

    @property
    def depth(
        self,
    ) -> int:
        return (
            self.projection_space
            .depth
        )

    @property
    def height(
        self,
    ) -> int:
        return (
            self.projection_space
            .height
        )

    @property
    def voxel_size(
        self,
    ) -> float:
        return (
            self.projection_space
            .voxel_size
        )

    @property
    def center_xy(
        self,
    ) -> bool:
        return (
            self.projection_space
            .center_xy
        )

    @property
    def projection_dimensions(
        self,
    ) -> tuple[
        int,
        int,
        int,
    ]:
        return (
            self.projection_space
            .dimensions
        )

    # -----------------------------------------------------
    # Surface object helpers
    # -----------------------------------------------------

    @property
    def object_name(
        self,
    ) -> str:
        name = getattr(
            self.blender_object,
            "name",
            None,
        )

        if name is None:
            return (
                type(
                    self.blender_object
                )
                .__name__
            )

        return str(
            name
        )

    @property
    def vertex_count(
        self,
    ) -> int | None:
        """
        Best-effort generic vertex count.

        Explicit metrics win.

        Blender-specific inspection is only attempted through
        attribute access so this module remains bpy-free.
        """

        if (
            "vertex_count"
            in self.metrics
        ):
            try:
                return int(
                    self.metrics[
                        "vertex_count"
                    ]
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        data = getattr(
            self.blender_object,
            "data",
            None,
        )

        vertices = getattr(
            data,
            "vertices",
            None,
        )

        if vertices is None:
            return None

        try:
            return len(
                vertices
            )

        except TypeError:
            return None

    @property
    def polygon_count(
        self,
    ) -> int | None:
        """
        Best-effort generic polygon count.
        """

        if (
            "polygon_count"
            in self.metrics
        ):
            try:
                return int(
                    self.metrics[
                        "polygon_count"
                    ]
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        data = getattr(
            self.blender_object,
            "data",
            None,
        )

        polygons = getattr(
            data,
            "polygons",
            None,
        )

        if polygons is None:
            return None

        try:
            return len(
                polygons
            )

        except TypeError:
            return None

    # -----------------------------------------------------
    # Convenience
    # -----------------------------------------------------

    def projection_kwargs(
        self,
    ) -> dict[
        str,
        Any,
    ]:
        return (
            self.projection_space
            .as_projection_kwargs()
        )


# =========================================================
# Validation
# =========================================================

def validate_geometry_surface_output(
    output: Any,
) -> GeometrySurfaceOutput:
    """
    Validate and return a generic GEOMETRY result.

    Keeping this check in one place makes failures explicit
    when an implementation accidentally returns an old,
    implementation-specific contract.
    """

    if not isinstance(
        output,
        GeometrySurfaceOutput,
    ):
        raise TypeError(
            (
                "GEOMETRY output must implement "
                "GeometrySurfaceOutput. "
                "Received "
                f"{type(output).__name__}."
            )
        )

    if (
        output.blender_object
        is None
    ):
        raise ValueError(
            (
                "GEOMETRY output contains "
                "no surface object."
            )
        )

    if (
        output.source
        is None
    ):
        raise ValueError(
            (
                "GEOMETRY output contains "
                "no INPUT source."
            )
        )

    # Accessing projection kwargs also validates the
    # coordinate convention currently understood by the
    # projection/material stack.

    output.projection_space.as_projection_kwargs()

    return output


# =========================================================
# PipelineContext accessor
# =========================================================

def require_geometry_surface_output(
    context: PipelineContext,
) -> GeometrySurfaceOutput:
    """
    Generic typed accessor for every downstream pipeline
    stage.

    This replaces implementation-specific accessors such as:

        require_native_visual_hull_output(context)

    inside MATERIAL implementations.

    Concrete geometry code may still expose its own accessor
    for implementation-specific tooling and diagnostics.
    """

    output = (
        context.require_output(
            PipelineStage.GEOMETRY
        )
    )

    try:
        return (
            validate_geometry_surface_output(
                output
            )
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise TypeError(
            (
                "Pipeline GEOMETRY output is "
                "not compatible with the "
                "generic surface contract. "
                f"Received "
                f"{type(output).__name__}."
            )
        ) from exc


# =========================================================
# Public API
# =========================================================

__all__ = (
    "DEFAULT_PROJECTION_CONVENTION",
    "GeometryProjectionConvention",
    "GeometryProjectionSpace",
    "GeometrySurfaceOutput",
    "require_geometry_surface_output",
    "validate_geometry_surface_output",
)