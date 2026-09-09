from __future__ import annotations

import math

from dataclasses import dataclass


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

EPSILON = 1e-9


# ---------------------------------------------------------
# Data
# ---------------------------------------------------------

@dataclass(frozen=True)
class NormalizedPoint:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class ProjectedPoint:
    u: float
    v: float

    @property
    def inside(self) -> bool:
        return (
            0.0 <= self.u <= 1.0
            and 0.0 <= self.v <= 1.0
        )


@dataclass(frozen=True)
class ProjectionTransform:
    """
    Precompiled projection transform.

    The fields intentionally mirror the native
    C++ CompiledProjection transform used by
    visual_hull.cpp.

    `sin_az` and `sin_el` already contain the
    inverse-camera sign convention used by the
    native engine.
    """

    azimuth_degrees: float
    elevation_degrees: float

    cos_az: float
    sin_az: float

    cos_el: float
    sin_el: float

    horizontal_extent: float
    vertical_extent: float

    flip_x: bool


# ---------------------------------------------------------
# Native-compatible grid normalization
# ---------------------------------------------------------

def grid_to_normalized(
    value: float,
    size: int,
) -> float:
    """
    Reproduce the native visual-hull grid mapping.

    Native voxel samples:

        0          -> -1
        size - 1   -> +1

    This function corresponds directly to
    grid_to_normalized() in visual_hull.cpp.
    """

    if size <= 1:
        return 0.0

    return (
        (
            float(value)
            / float(
                size - 1
            )
        )
        * 2.0
        - 1.0
    )


# ---------------------------------------------------------
# Surface mesh -> normalized reconstruction space
# ---------------------------------------------------------

def surface_position_to_normalized(
    position: tuple[
        float,
        float,
        float,
    ],
    *,
    width: int,
    depth: int,
    height: int,
    voxel_size: float = 1.0,
    center_xy: bool = True,
) -> NormalizedPoint:
    """
    Convert a generated mesh position into the
    normalized reconstruction domain expected by
    project_normalized_point().

    Important distinction:

    The native visual hull evaluates VOXEL CENTRES
    using grid_to_normalized():

        voxel index 0          -> -1
        voxel index size - 1   -> +1

    The generated surface mesh represents the
    OUTER ENVELOPE of those voxels:

        X: 0 .. width
        Y: 0 .. depth
        Z: 0 .. height

    Therefore material projection should normalize
    the surface envelope rather than treating a
    boundary vertex as a voxel centre.

    This prevents the outer half-voxel of the mesh
    from projecting outside [0, 1].
    """

    if (
        width <= 0
        or depth <= 0
        or height <= 0
    ):
        raise ValueError(
            (
                "Volume dimensions must be "
                "greater than zero."
            )
        )

    if voxel_size <= 0.0:
        raise ValueError(
            (
                "voxel_size must be "
                "greater than zero."
            )
        )

    (
        x,
        y,
        z,
    ) = position

    # -----------------------------------------------------
    # Recover grid-envelope coordinates.
    #
    # BLOCKS and Surface Nets share the same historical
    # XY centering convention:
    #
    #   world_x =
    #       grid_x * voxel_size
    #       - width * voxel_size / 2
    #
    # Z is intentionally not centered.
    # -----------------------------------------------------

    if center_xy:
        grid_x = (
            float(x)
            / voxel_size
            + float(width)
            * 0.5
        )

        grid_y = (
            float(y)
            / voxel_size
            + float(depth)
            * 0.5
        )

    else:
        grid_x = (
            float(x)
            / voxel_size
        )

        grid_y = (
            float(y)
            / voxel_size
        )

    grid_z = (
        float(z)
        / voxel_size
    )

    # -----------------------------------------------------
    # Surface envelope mapping:
    #
    #   0       -> -1
    #   extent  -> +1
    #
    # Unlike grid_to_normalized(), the denominator here
    # is the full voxel extent rather than size - 1.
    # -----------------------------------------------------

    nx = (
        (
            grid_x
            / float(width)
        )
        * 2.0
        - 1.0
    )

    ny = (
        (
            grid_y
            / float(depth)
        )
        * 2.0
        - 1.0
    )

    nz = (
        (
            grid_z
            / float(height)
        )
        * 2.0
        - 1.0
    )

    return NormalizedPoint(
        x=nx,
        y=ny,
        z=nz,
    )


# ---------------------------------------------------------
# Projection compilation
# ---------------------------------------------------------

def compile_projection(
    *,
    azimuth_degrees: float,
    elevation_degrees: float,
    flip_x: bool = False,
) -> ProjectionTransform:
    """
    Compile the same projection transform used by
    the native visual-hull engine.

    Keep this implementation deliberately close to
    visual_hull.cpp so geometry reconstruction and
    material projection do not slowly diverge.
    """

    azimuth = math.radians(
        float(
            azimuth_degrees
        )
    )

    elevation = math.radians(
        float(
            elevation_degrees
        )
    )

    cos_az = math.cos(
        azimuth
    )

    sin_az = math.sin(
        azimuth
    )

    cos_el = math.cos(
        elevation
    )

    sin_el = math.sin(
        elevation
    )

    horizontal_extent = max(
        abs(
            cos_az
        )
        + abs(
            sin_az
        ),
        EPSILON,
    )

    vertical_extent = max(
        (
            horizontal_extent
            * abs(
                sin_el
            )
        )
        + abs(
            cos_el
        ),
        EPSILON,
    )

    return ProjectionTransform(
        azimuth_degrees=(
            float(
                azimuth_degrees
            )
        ),
        elevation_degrees=(
            float(
                elevation_degrees
            )
        ),

        # Same inverse-camera convention
        # as native visual_hull.cpp.
        cos_az=cos_az,
        sin_az=-sin_az,

        cos_el=cos_el,
        sin_el=-sin_el,

        horizontal_extent=(
            horizontal_extent
        ),
        vertical_extent=(
            vertical_extent
        ),

        flip_x=bool(
            flip_x
        ),
    )


# ---------------------------------------------------------
# Projection
# ---------------------------------------------------------

def project_normalized_point(
    point: NormalizedPoint,
    transform: ProjectionTransform,
) -> ProjectedPoint:
    """
    Project one normalized 3D point into image UV space.

    This reproduces the geometry portion of the
    native sample_projection() implementation.

    UV convention:

        u = 0 -> image left
        u = 1 -> image right

        v = 0 -> image bottom
        v = 1 -> image top

    This matches Blender image pixel storage and the
    mask extraction pipeline.
    """

    nx = float(
        point.x
    )

    ny = float(
        point.y
    )

    nz = float(
        point.z
    )

    x1 = (
        nx
        * transform.cos_az
        -
        ny
        * transform.sin_az
    )

    y1 = (
        nx
        * transform.sin_az
        +
        ny
        * transform.cos_az
    )

    z2 = (
        y1
        * transform.sin_el
        +
        nz
        * transform.cos_el
    )

    u = (
        (
            (
                x1
                / transform
                .horizontal_extent
            )
            + 1.0
        )
        * 0.5
    )

    v = (
        (
            (
                z2
                / transform
                .vertical_extent
            )
            + 1.0
        )
        * 0.5
    )

    if transform.flip_x:
        u = (
            1.0
            - u
        )

    return ProjectedPoint(
        u=u,
        v=v,
    )


def project_surface_position(
    position: tuple[
        float,
        float,
        float,
    ],
    *,
    transform: ProjectionTransform,
    width: int,
    depth: int,
    height: int,
    voxel_size: float = 1.0,
    center_xy: bool = True,
) -> ProjectedPoint:
    """
    Convenience wrapper:

        Blender mesh position
                ↓
        normalized reconstruction space
                ↓
        projection UV
    """

    normalized = (
        surface_position_to_normalized(
            position,
            width=width,
            depth=depth,
            height=height,
            voxel_size=voxel_size,
            center_xy=center_xy,
        )
    )

    return project_normalized_point(
        normalized,
        transform,
    )


# ---------------------------------------------------------
# View direction
# ---------------------------------------------------------

def direction_to_camera(
    *,
    azimuth_degrees: float,
    elevation_degrees: float,
) -> tuple[
    float,
    float,
    float,
]:
    """
    Unit direction from the object toward the camera.

    This follows the same camera convention as the
    Projection Tool preview renderer:

        azimuth 0°
            camera on -Y

        azimuth 90°
            camera on +X

        elevation +90°
            camera above the object

    This direction will later be used for normal-based
    multi-view weighting.
    """

    azimuth = math.radians(
        float(
            azimuth_degrees
        )
    )

    elevation = math.radians(
        float(
            elevation_degrees
        )
    )

    horizontal = math.cos(
        elevation
    )

    return (
        math.sin(
            azimuth
        )
        * horizontal,

        -math.cos(
            azimuth
        )
        * horizontal,

        math.sin(
            elevation
        ),
    )


# ---------------------------------------------------------
# Small helpers
# ---------------------------------------------------------

def clamp01(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(
                value
            ),
        ),
    )


def dot3(
    a: tuple[
        float,
        float,
        float,
    ],
    b: tuple[
        float,
        float,
        float,
    ],
) -> float:
    return (
        a[0]
        * b[0]
        + a[1]
        * b[1]
        + a[2]
        * b[2]
    )


def normalize3(
    value: tuple[
        float,
        float,
        float,
    ],
) -> tuple[
    float,
    float,
    float,
]:
    length = math.sqrt(
        (
            value[0]
            * value[0]
        )
        + (
            value[1]
            * value[1]
        )
        + (
            value[2]
            * value[2]
        )
    )

    if length <= EPSILON:
        return (
            0.0,
            0.0,
            0.0,
        )

    inverse = (
        1.0
        / length
    )

    return (
        value[0]
        * inverse,

        value[1]
        * inverse,

        value[2]
        * inverse,
    )