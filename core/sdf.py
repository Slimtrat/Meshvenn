from __future__ import annotations

import math

from array import array
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Iterable,
    Sequence,
)

from .image_mask import (
    BinaryMask,
)
from .projection_math import (
    NormalizedPoint,
    ProjectionTransform,
    compile_projection,
    grid_to_normalized,
    project_normalized_point,
)


# =========================================================
# Constants
# =========================================================

SIGN_EPSILON = 1e-9

DEFAULT_ISO_LEVEL = 0.0

DEFAULT_SMOOTHNESS = 0.0

DEFAULT_SURFACE_OFFSET = 0.0

DEFAULT_SYMMETRY_X = False


# ---------------------------------------------------------
# Pure-Python reference guard
#
# SDF V1 starts with a deterministic Python reference
# implementation.
#
# Production-sized fields will later move to the native C++
# layer while preserving exactly the contracts and semantics
# defined here.
#
# 4,194,304 samples ~= 160^3.
# ---------------------------------------------------------

DEFAULT_REFERENCE_MAX_VOXELS = (
    4_194_304
)


# =========================================================
# Small numeric helpers
# =========================================================

def _require_finite(
    value: float,
    *,
    name: str,
) -> float:
    result = float(
        value
    )

    if not math.isfinite(
        result
    ):
        raise ValueError(
            (
                f"{name} must be finite."
            )
        )

    return result


def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            float(
                value
            ),
        ),
    )


def _lerp(
    a: float,
    b: float,
    t: float,
) -> float:
    return (
        float(a)
        + (
            float(b)
            - float(a)
        )
        * float(t)
    )


# =========================================================
# Exact 1D squared Euclidean distance transform
# =========================================================

def _distance_transform_1d(
    values: Sequence[
        float
    ],
    *,
    spacing: float,
) -> list[
    float
]:
    """
    Exact lower-envelope squared-distance transform.

    For every output position i:

        result[i] =
            min_j(
                values[j]
                + ((i - j) * spacing)^2
            )

    Infinite entries mean:

        no feature at that location

    This is the separable parabola-envelope algorithm used
    to build the exact 2D Euclidean distance field without
    an O(N^2) search per pixel.

    `spacing` allows anisotropic image-space metrics.
    """

    count = len(
        values
    )

    if count == 0:
        return []

    spacing = _require_finite(
        spacing,
        name="spacing",
    )

    if spacing <= 0.0:
        raise ValueError(
            (
                "spacing must be greater "
                "than zero."
            )
        )

    finite_sites = [
        index
        for (
            index,
            value,
        ) in enumerate(
            values
        )
        if math.isfinite(
            float(
                value
            )
        )
    ]

    if not finite_sites:
        return [
            math.inf
        ] * count

    # -----------------------------------------------------
    # sites[k]
    #
    #     parabola selected for one interval
    #
    # starts[k]
    #
    #     world-space coordinate where that parabola becomes
    #     better than the previous one
    # -----------------------------------------------------

    sites: list[
        int
    ] = [
        finite_sites[0]
    ]

    starts: list[
        float
    ] = [
        -math.inf
    ]

    def intersection(
        left_index: int,
        right_index: int,
    ) -> float:
        left_x = (
            float(
                left_index
            )
            * spacing
        )

        right_x = (
            float(
                right_index
            )
            * spacing
        )

        left_value = float(
            values[
                left_index
            ]
        )

        right_value = float(
            values[
                right_index
            ]
        )

        numerator = (
            right_value
            + right_x
            * right_x
            - left_value
            - left_x
            * left_x
        )

        denominator = (
            2.0
            * (
                right_x
                - left_x
            )
        )

        return (
            numerator
            / denominator
        )

    for site in (
        finite_sites[1:]
    ):
        start = intersection(
            sites[-1],
            site,
        )

        while (
            len(
                sites
            )
            > 1
            and start
            <= starts[-1]
        ):
            sites.pop()
            starts.pop()

            start = intersection(
                sites[-1],
                site,
            )

        sites.append(
            site
        )

        starts.append(
            start
        )

    result = [
        0.0
    ] * count

    active = 0

    for index in range(
        count
    ):
        x = (
            float(
                index
            )
            * spacing
        )

        while (
            active + 1
            < len(
                sites
            )
            and x
            >= starts[
                active + 1
            ]
        ):
            active += 1

        site = (
            sites[
                active
            ]
        )

        site_x = (
            float(
                site
            )
            * spacing
        )

        delta = (
            x
            - site_x
        )

        result[
            index
        ] = (
            float(
                values[
                    site
                ]
            )
            + delta
            * delta
        )

    return result


# =========================================================
# 2D Euclidean distance transform
# =========================================================

def _squared_distance_to_mask_value(
    mask: BinaryMask,
    *,
    target_inside: bool,
    horizontal_spacing: float,
    vertical_spacing: float,
) -> array:
    """
    Return squared distance from every pixel centre to the
    closest pixel whose binary state equals `target_inside`.

    Result layout:

        row-major
        y * width + x
    """

    width = int(
        mask.width
    )

    height = int(
        mask.height
    )

    pixel_count = (
        width
        * height
    )

    horizontal_spacing = (
        _require_finite(
            horizontal_spacing,
            name=(
                "horizontal_spacing"
            ),
        )
    )

    vertical_spacing = (
        _require_finite(
            vertical_spacing,
            name=(
                "vertical_spacing"
            ),
        )
    )

    if horizontal_spacing <= 0.0:
        raise ValueError(
            (
                "horizontal_spacing must "
                "be greater than zero."
            )
        )

    if vertical_spacing <= 0.0:
        raise ValueError(
            (
                "vertical_spacing must "
                "be greater than zero."
            )
        )

    source = (
        mask.values
    )

    intermediate = array(
        "d",
        [
            math.inf
        ],
    ) * pixel_count

    # -----------------------------------------------------
    # Horizontal pass
    # -----------------------------------------------------

    for y in range(
        height
    ):
        row_start = (
            y
            * width
        )

        row = [
            (
                0.0
                if (
                    bool(
                        source[
                            row_start
                            + x
                        ]
                    )
                    == target_inside
                )
                else math.inf
            )
            for x
            in range(
                width
            )
        ]

        transformed = (
            _distance_transform_1d(
                row,
                spacing=(
                    horizontal_spacing
                ),
            )
        )

        for (
            x,
            value,
        ) in enumerate(
            transformed
        ):
            intermediate[
                row_start
                + x
            ] = value

    # -----------------------------------------------------
    # Vertical pass
    # -----------------------------------------------------

    result = array(
        "d",
        [
            math.inf
        ],
    ) * pixel_count

    for x in range(
        width
    ):
        column = [
            intermediate[
                y
                * width
                + x
            ]
            for y
            in range(
                height
            )
        ]

        transformed = (
            _distance_transform_1d(
                column,
                spacing=(
                    vertical_spacing
                ),
            )
        )

        for (
            y,
            value,
        ) in enumerate(
            transformed
        ):
            result[
                y
                * width
                + x
            ] = value

    return result


# =========================================================
# Signed 2D silhouette field
# =========================================================

@dataclass(frozen=True)
class SignedDistanceMask:
    """
    Continuous signed-distance representation of one
    silhouette.

    Sign convention:

        negative
            inside silhouette

        zero
            silhouette boundary

        positive
            outside silhouette

    Distances are expressed in normalized reconstruction
    plane units, not raw image pixels.

    For one projection:

        U extent =
            [-horizontal_extent, +horizontal_extent]

        V extent =
            [-vertical_extent, +vertical_extent]

    Consequently fields coming from differently-sized source
    images remain comparable during multi-view fusion.
    """

    width: int

    height: int

    values: array

    horizontal_extent: float

    vertical_extent: float

    occupied_count: int

    def __post_init__(
        self,
    ) -> None:
        if self.width <= 0:
            raise ValueError(
                (
                    "Signed-distance mask width "
                    "must be positive."
                )
            )

        if self.height <= 0:
            raise ValueError(
                (
                    "Signed-distance mask height "
                    "must be positive."
                )
            )

        horizontal_extent = (
            _require_finite(
                self.horizontal_extent,
                name=(
                    "horizontal_extent"
                ),
            )
        )

        vertical_extent = (
            _require_finite(
                self.vertical_extent,
                name=(
                    "vertical_extent"
                ),
            )
        )

        if horizontal_extent <= 0.0:
            raise ValueError(
                (
                    "horizontal_extent must "
                    "be positive."
                )
            )

        if vertical_extent <= 0.0:
            raise ValueError(
                (
                    "vertical_extent must "
                    "be positive."
                )
            )

        expected_count = (
            self.width
            * self.height
        )

        copied = array(
            "f",
            self.values,
        )

        if len(
            copied
        ) != expected_count:
            raise ValueError(
                (
                    "Signed-distance mask contains "
                    f"{len(copied)} values, "
                    f"expected {expected_count}."
                )
            )

        for value in copied:
            if not math.isfinite(
                float(
                    value
                )
            ):
                raise ValueError(
                    (
                        "Signed-distance mask "
                        "contains a non-finite value."
                    )
                )

        occupied_count = int(
            self.occupied_count
        )

        if (
            occupied_count < 0
            or occupied_count
            > expected_count
        ):
            raise ValueError(
                (
                    "occupied_count is outside "
                    "the valid mask range."
                )
            )

        object.__setattr__(
            self,
            "horizontal_extent",
            horizontal_extent,
        )

        object.__setattr__(
            self,
            "vertical_extent",
            vertical_extent,
        )

        object.__setattr__(
            self,
            "occupied_count",
            occupied_count,
        )

        object.__setattr__(
            self,
            "values",
            copied,
        )

    # -----------------------------------------------------
    # Domain
    # -----------------------------------------------------

    @property
    def pixel_count(
        self,
    ) -> int:
        return (
            self.width
            * self.height
        )

    @property
    def domain_width(
        self,
    ) -> float:
        return (
            self.horizontal_extent
            * 2.0
        )

    @property
    def domain_height(
        self,
    ) -> float:
        return (
            self.vertical_extent
            * 2.0
        )

    @property
    def horizontal_spacing(
        self,
    ) -> float:
        if self.width <= 1:
            return (
                self.domain_width
            )

        return (
            self.domain_width
            / float(
                self.width - 1
            )
        )

    @property
    def vertical_spacing(
        self,
    ) -> float:
        if self.height <= 1:
            return (
                self.domain_height
            )

        return (
            self.domain_height
            / float(
                self.height - 1
            )
        )

    @property
    def empty(
        self,
    ) -> bool:
        return (
            self.occupied_count
            == 0
        )

    @property
    def full(
        self,
    ) -> bool:
        return (
            self.occupied_count
            == self.pixel_count
        )

    # -----------------------------------------------------
    # Pixel access
    # -----------------------------------------------------

    def get(
        self,
        x: int,
        y: int,
    ) -> float:
        if (
            x < 0
            or x >= self.width
            or y < 0
            or y >= self.height
        ):
            raise IndexError(
                (
                    "Signed-distance mask "
                    "coordinate outside bounds."
                )
            )

        return float(
            self.values[
                y
                * self.width
                + x
            ]
        )

    # -----------------------------------------------------
    # Bilinear sampling
    # -----------------------------------------------------

    def _sample_clamped_uv(
        self,
        u: float,
        v: float,
    ) -> float:
        u = _clamp(
            u,
            0.0,
            1.0,
        )

        v = _clamp(
            v,
            0.0,
            1.0,
        )

        if self.width <= 1:
            x = 0.0
        else:
            x = (
                u
                * float(
                    self.width - 1
                )
            )

        if self.height <= 1:
            y = 0.0
        else:
            y = (
                v
                * float(
                    self.height - 1
                )
            )

        x0 = int(
            math.floor(
                x
            )
        )

        y0 = int(
            math.floor(
                y
            )
        )

        x1 = min(
            x0 + 1,
            self.width - 1,
        )

        y1 = min(
            y0 + 1,
            self.height - 1,
        )

        tx = (
            x
            - float(
                x0
            )
        )

        ty = (
            y
            - float(
                y0
            )
        )

        a = self.get(
            x0,
            y0,
        )

        b = self.get(
            x1,
            y0,
        )

        c = self.get(
            x0,
            y1,
        )

        d = self.get(
            x1,
            y1,
        )

        bottom = _lerp(
            a,
            b,
            tx,
        )

        top = _lerp(
            c,
            d,
            tx,
        )

        return _lerp(
            bottom,
            top,
            ty,
        )

    def sample_uv(
        self,
        u: float,
        v: float,
    ) -> float:
        """
        Sample continuous signed distance in projection UV.

        Points outside [0, 1]^2 are necessarily outside the
        silhouette, matching the historical visual-hull rule.

        We extend the field with a positive distance from the
        image boundary.
        """

        u = _require_finite(
            u,
            name="u",
        )

        v = _require_finite(
            v,
            name="v",
        )

        clamped_u = _clamp(
            u,
            0.0,
            1.0,
        )

        clamped_v = _clamp(
            v,
            0.0,
            1.0,
        )

        edge_value = (
            self._sample_clamped_uv(
                clamped_u,
                clamped_v,
            )
        )

        if (
            0.0 <= u <= 1.0
            and 0.0 <= v <= 1.0
        ):
            return edge_value

        if u < 0.0:
            outside_x = (
                -u
                * self.domain_width
            )

        elif u > 1.0:
            outside_x = (
                (
                    u
                    - 1.0
                )
                * self.domain_width
            )

        else:
            outside_x = 0.0

        if v < 0.0:
            outside_y = (
                -v
                * self.domain_height
            )

        elif v > 1.0:
            outside_y = (
                (
                    v
                    - 1.0
                )
                * self.domain_height
            )

        else:
            outside_y = 0.0

        outside_distance = math.hypot(
            outside_x,
            outside_y,
        )

        return (
            outside_distance
            + max(
                0.0,
                edge_value,
            )
        )


# =========================================================
# Binary mask -> signed-distance mask
# =========================================================

def build_signed_distance_mask(
    mask: BinaryMask,
    *,
    horizontal_extent: float = 1.0,
    vertical_extent: float = 1.0,
) -> SignedDistanceMask:
    """
    Convert a BinaryMask into an exact Euclidean signed
    distance field.

    The distance metric is expressed in the projected plane
    of the normalized reconstruction domain.

    Important boundary rule:

        outside the source image = background

    Therefore foreground pixels touching an image edge use
    the image rectangle itself as a valid outside boundary.
    """

    if not isinstance(
        mask,
        BinaryMask,
    ):
        raise TypeError(
            (
                "mask must be BinaryMask."
            )
        )

    horizontal_extent = (
        _require_finite(
            horizontal_extent,
            name=(
                "horizontal_extent"
            ),
        )
    )

    vertical_extent = (
        _require_finite(
            vertical_extent,
            name=(
                "vertical_extent"
            ),
        )
    )

    if horizontal_extent <= 0.0:
        raise ValueError(
            (
                "horizontal_extent must "
                "be positive."
            )
        )

    if vertical_extent <= 0.0:
        raise ValueError(
            (
                "vertical_extent must "
                "be positive."
            )
        )

    width = int(
        mask.width
    )

    height = int(
        mask.height
    )

    domain_width = (
        horizontal_extent
        * 2.0
    )

    domain_height = (
        vertical_extent
        * 2.0
    )

    horizontal_spacing = (
        domain_width
        / float(
            width - 1
        )
        if width > 1
        else domain_width
    )

    vertical_spacing = (
        domain_height
        / float(
            height - 1
        )
        if height > 1
        else domain_height
    )

    # -----------------------------------------------------
    # Distance to silhouette.
    #
    # Used by background pixels.
    # -----------------------------------------------------

    distance_to_inside_sq = (
        _squared_distance_to_mask_value(
            mask,
            target_inside=True,
            horizontal_spacing=(
                horizontal_spacing
            ),
            vertical_spacing=(
                vertical_spacing
            ),
        )
    )

    # -----------------------------------------------------
    # Distance to background pixels.
    #
    # Used by silhouette pixels.
    # -----------------------------------------------------

    distance_to_outside_sq = (
        _squared_distance_to_mask_value(
            mask,
            target_inside=False,
            horizontal_spacing=(
                horizontal_spacing
            ),
            vertical_spacing=(
                vertical_spacing
            ),
        )
    )

    pixel_count = (
        width
        * height
    )

    output = array(
        "f",
        [
            0.0
        ],
    ) * pixel_count

    occupied_count = 0

    # No silhouette exists at all.
    #
    # Exact mathematical distance to foreground is infinite,
    # but keeping the reference field finite simplifies every
    # later consumer while preserving the only important
    # property:
    #
    #     every sample is outside.
    empty_fallback_distance = (
        math.hypot(
            domain_width,
            domain_height,
        )
        + max(
            horizontal_spacing,
            vertical_spacing,
        )
    )

    source = (
        mask.values
    )

    for y in range(
        height
    ):
        for x in range(
            width
        ):
            index = (
                y
                * width
                + x
            )

            inside = bool(
                source[
                    index
                ]
            )

            if inside:
                occupied_count += 1

                internal_squared = (
                    distance_to_outside_sq[
                        index
                    ]
                )

                if math.isfinite(
                    internal_squared
                ):
                    internal_distance = (
                        math.sqrt(
                            max(
                                0.0,
                                internal_squared,
                            )
                        )
                    )

                else:
                    internal_distance = (
                        math.inf
                    )

                # -----------------------------------------
                # The world outside the source image is
                # background.
                #
                # Pixel centres lie half a pixel from that
                # outer boundary.
                # -----------------------------------------

                border_distance = min(
                    (
                        float(x)
                        + 0.5
                    )
                    * horizontal_spacing,

                    (
                        float(
                            width - 1 - x
                        )
                        + 0.5
                    )
                    * horizontal_spacing,

                    (
                        float(y)
                        + 0.5
                    )
                    * vertical_spacing,

                    (
                        float(
                            height - 1 - y
                        )
                        + 0.5
                    )
                    * vertical_spacing,
                )

                distance = min(
                    internal_distance,
                    border_distance,
                )

                output[
                    index
                ] = (
                    -float(
                        distance
                    )
                )

            else:
                squared = (
                    distance_to_inside_sq[
                        index
                    ]
                )

                if math.isfinite(
                    squared
                ):
                    distance = math.sqrt(
                        max(
                            0.0,
                            squared,
                        )
                    )

                else:
                    distance = (
                        empty_fallback_distance
                    )

                output[
                    index
                ] = float(
                    distance
                )

    return SignedDistanceMask(
        width=width,
        height=height,
        values=output,
        horizontal_extent=(
            horizontal_extent
        ),
        vertical_extent=(
            vertical_extent
        ),
        occupied_count=(
            occupied_count
        ),
    )


# =========================================================
# One SDF projection
# =========================================================

@dataclass(frozen=True)
class SDFProjection:
    """
    One silhouette constraint converted to continuous signed
    distance.

        BinaryMask
            ↓
        2D signed distance
            ↓
        ProjectionTransform
            ↓
        continuous 3D prism constraint

    The constraint is negative anywhere whose orthographic
    projection lies inside the silhouette.
    """

    name: str

    transform: ProjectionTransform

    field: SignedDistanceMask

    def __post_init__(
        self,
    ) -> None:
        name = str(
            self.name
        ).strip()

        if not name:
            name = "Projection"

        object.__setattr__(
            self,
            "name",
            name,
        )

        if not isinstance(
            self.transform,
            ProjectionTransform,
        ):
            raise TypeError(
                (
                    "transform must be "
                    "ProjectionTransform."
                )
            )

        if not isinstance(
            self.field,
            SignedDistanceMask,
        ):
            raise TypeError(
                (
                    "field must be "
                    "SignedDistanceMask."
                )
            )

        if not math.isclose(
            self.field.horizontal_extent,
            self.transform.horizontal_extent,
            rel_tol=1e-7,
            abs_tol=1e-7,
        ):
            raise ValueError(
                (
                    "Signed-distance horizontal "
                    "extent does not match "
                    "projection transform."
                )
            )

        if not math.isclose(
            self.field.vertical_extent,
            self.transform.vertical_extent,
            rel_tol=1e-7,
            abs_tol=1e-7,
        ):
            raise ValueError(
                (
                    "Signed-distance vertical "
                    "extent does not match "
                    "projection transform."
                )
            )

    @property
    def width(
        self,
    ) -> int:
        return (
            self.field.width
        )

    @property
    def height(
        self,
    ) -> int:
        return (
            self.field.height
        )

    @property
    def empty(
        self,
    ) -> bool:
        return (
            self.field.empty
        )

    def sample(
        self,
        point: NormalizedPoint,
    ) -> float:
        projected = (
            project_normalized_point(
                point,
                self.transform,
            )
        )

        return (
            self.field.sample_uv(
                projected.u,
                projected.v,
            )
        )

    @classmethod
    def from_mask(
        cls,
        mask: BinaryMask,
        *,
        azimuth_degrees: float,
        elevation_degrees: float,
        flip_x: bool = False,
        name: str = "Projection",
    ) -> "SDFProjection":
        transform = (
            compile_projection(
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

        field = (
            build_signed_distance_mask(
                mask,
                horizontal_extent=(
                    transform
                    .horizontal_extent
                ),
                vertical_extent=(
                    transform
                    .vertical_extent
                ),
            )
        )

        return cls(
            name=name,
            transform=transform,
            field=field,
        )

    @classmethod
    def from_source_view(
        cls,
        view: Any,
    ) -> "SDFProjection":
        """
        Capability-based adapter for Projection Images and
        future INPUT implementations.

        Required attributes:

            mask
            azimuth_degrees
            elevation_degrees

        Optional:

            flip_x
            name
        """

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
                    "Source view does not expose "
                    "a BinaryMask."
                )
            )

        return cls.from_mask(
            mask,

            azimuth_degrees=float(
                getattr(
                    view,
                    "azimuth_degrees",
                )
            ),

            elevation_degrees=float(
                getattr(
                    view,
                    "elevation_degrees",
                )
            ),

            flip_x=bool(
                getattr(
                    view,
                    "flip_x",
                    False,
                )
            ),

            name=str(
                getattr(
                    view,
                    "name",
                    "Projection",
                )
            ),
        )


def build_sdf_projections(
    views: Iterable[
        Any
    ],
) -> tuple[
    SDFProjection,
    ...
]:
    result = tuple(
        SDFProjection
        .from_source_view(
            view
        )
        for view
        in views
    )

    if not result:
        raise ValueError(
            (
                "At least one projection "
                "is required."
            )
        )

    return result


# =========================================================
# SDF CSG
# =========================================================

def smooth_max(
    a: float,
    b: float,
    smoothness: float,
) -> float:
    """
    Polynomial smooth maximum.

    For signed distance fields:

        max(a, b)

    represents CSG intersection.

    smooth_max() rounds the transition between two
    constraints while remaining local to a band of width
    `smoothness`.

    smoothness == 0
        exact hard intersection
    """

    a = _require_finite(
        a,
        name="a",
    )

    b = _require_finite(
        b,
        name="b",
    )

    smoothness = (
        _require_finite(
            smoothness,
            name="smoothness",
        )
    )

    if smoothness < 0.0:
        raise ValueError(
            (
                "smoothness cannot "
                "be negative."
            )
        )

    if smoothness <= 0.0:
        return max(
            a,
            b,
        )

    difference = abs(
        a
        - b
    )

    if difference >= smoothness:
        return max(
            a,
            b,
        )

    h = (
        (
            smoothness
            - difference
        )
        / smoothness
    )

    return (
        max(
            a,
            b,
        )
        + (
            h
            * h
            * smoothness
            * 0.25
        )
    )


def fuse_signed_distances(
    distances: Iterable[
        float
    ],
    *,
    smoothness: float = (
        DEFAULT_SMOOTHNESS
    ),
) -> float:
    """
    Intersect multiple signed-distance constraints.

    Hard visual-hull equivalent:

        max(d0, d1, d2, ...)

    Negative survives only if every projection constraint is
    negative.

    This is the continuous equivalent of silhouette
    intersection.
    """

    values = tuple(
        _require_finite(
            value,
            name="distance",
        )
        for value
        in distances
    )

    if not values:
        raise ValueError(
            (
                "At least one signed distance "
                "is required for fusion."
            )
        )

    smoothness = (
        _require_finite(
            smoothness,
            name="smoothness",
        )
    )

    if smoothness < 0.0:
        raise ValueError(
            (
                "smoothness cannot "
                "be negative."
            )
        )

    result = (
        values[0]
    )

    for value in (
        values[1:]
    ):
        result = smooth_max(
            result,
            value,
            smoothness,
        )

    return result


def sample_fused_sdf(
    point: NormalizedPoint,
    projections: Sequence[
        SDFProjection
    ],
    *,
    symmetry_x: bool = (
        DEFAULT_SYMMETRY_X
    ),
    smoothness: float = (
        DEFAULT_SMOOTHNESS
    ),
    surface_offset: float = (
        DEFAULT_SURFACE_OFFSET
    ),
) -> float:
    """
    Evaluate the multi-view signed field at one normalized
    reconstruction position.

    symmetry_x follows the existing conservative Visual Hull
    behaviour:

        point must satisfy each projection
        AND
        mirrored-X point must satisfy each projection

    Positive surface_offset expands the zero level-set.

    Negative surface_offset contracts it.
    """

    if not projections:
        raise ValueError(
            (
                "At least one SDF projection "
                "is required."
            )
        )

    smoothness = (
        _require_finite(
            smoothness,
            name="smoothness",
        )
    )

    if smoothness < 0.0:
        raise ValueError(
            (
                "smoothness cannot "
                "be negative."
            )
        )

    surface_offset = (
        _require_finite(
            surface_offset,
            name="surface_offset",
        )
    )

    constraints: list[
        float
    ] = []

    mirrored = (
        NormalizedPoint(
            x=(
                -float(
                    point.x
                )
            ),
            y=float(
                point.y
            ),
            z=float(
                point.z
            ),
        )
        if symmetry_x
        else None
    )

    for projection in (
        projections
    ):
        if not isinstance(
            projection,
            SDFProjection,
        ):
            raise TypeError(
                (
                    "All projections must be "
                    "SDFProjection instances."
                )
            )

        distance = (
            projection.sample(
                point
            )
        )

        if mirrored is not None:
            mirrored_distance = (
                projection.sample(
                    mirrored
                )
            )

            # Conservative symmetry is itself another
            # intersection constraint.
            distance = smooth_max(
                distance,
                mirrored_distance,
                smoothness,
            )

        constraints.append(
            distance
        )

    fused = (
        fuse_signed_distances(
            constraints,
            smoothness=(
                smoothness
            ),
        )
    )

    return (
        fused
        - surface_offset
    )


# =========================================================
# 3D SDF volume
# =========================================================

@dataclass(frozen=True)
class SDFVolume:
    """
    Dense scalar field sampled on a regular normalized grid.

    Layout:

        x fastest

        index =
            (z * depth + y) * width + x

    Sign:

        value < iso
            inside

        value > iso
            outside

        value == iso
            surface
    """

    width: int

    depth: int

    height: int

    values: array

    iso_level: float = (
        DEFAULT_ISO_LEVEL
    )

    def __post_init__(
        self,
    ) -> None:
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
                or value < 2
            ):
                raise ValueError(
                    (
                        f"{name} must be an "
                        "integer >= 2."
                    )
                )

        expected = (
            self.width
            * self.depth
            * self.height
        )

        copied = array(
            "f",
            self.values,
        )

        if len(
            copied
        ) != expected:
            raise ValueError(
                (
                    "SDF volume contains "
                    f"{len(copied)} values, "
                    f"expected {expected}."
                )
            )

        for value in copied:
            if not math.isfinite(
                float(
                    value
                )
            ):
                raise ValueError(
                    (
                        "SDF volume contains "
                        "a non-finite sample."
                    )
                )

        iso_level = _require_finite(
            self.iso_level,
            name="iso_level",
        )

        object.__setattr__(
            self,
            "values",
            copied,
        )

        object.__setattr__(
            self,
            "iso_level",
            iso_level,
        )

    @property
    def sample_count(
        self,
    ) -> int:
        return (
            self.width
            * self.depth
            * self.height
        )

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

    def index(
        self,
        x: int,
        y: int,
        z: int,
    ) -> int:
        if (
            x < 0
            or x >= self.width
            or y < 0
            or y >= self.depth
            or z < 0
            or z >= self.height
        ):
            raise IndexError(
                (
                    "SDF volume coordinate "
                    "outside bounds."
                )
            )

        return (
            (
                z
                * self.depth
                + y
            )
            * self.width
            + x
        )

    def get(
        self,
        x: int,
        y: int,
        z: int,
    ) -> float:
        return float(
            self.values[
                self.index(
                    x,
                    y,
                    z,
                )
            ]
        )

    def inside(
        self,
        x: int,
        y: int,
        z: int,
        *,
        iso_level: float | None = None,
    ) -> bool:
        resolved_iso = (
            self.iso_level
            if iso_level is None
            else _require_finite(
                iso_level,
                name="iso_level",
            )
        )

        return (
            self.get(
                x,
                y,
                z,
            )
            <= resolved_iso
        )

    @property
    def minimum_value(
        self,
    ) -> float:
        return float(
            min(
                self.values
            )
        )

    @property
    def maximum_value(
        self,
    ) -> float:
        return float(
            max(
                self.values
            )
        )

    @property
    def has_inside_samples(
        self,
    ) -> bool:
        iso = (
            self.iso_level
        )

        return any(
            float(
                value
            )
            <= iso
            for value
            in self.values
        )

    @property
    def has_outside_samples(
        self,
    ) -> bool:
        iso = (
            self.iso_level
        )

        return any(
            float(
                value
            )
            > iso
            for value
            in self.values
        )

    @property
    def crosses_surface(
        self,
    ) -> bool:
        return (
            self.has_inside_samples
            and self.has_outside_samples
        )

    def to_occupancy_bytes(
        self,
        *,
        iso_level: float | None = None,
    ) -> bytes:
        """
        Diagnostic compatibility representation.

        IMPORTANT:

        converting the SDF to occupancy loses the continuous
        field advantage.

        Native SDF surface extraction should consume floats
        directly rather than using this function.
        """

        resolved_iso = (
            self.iso_level
            if iso_level is None
            else _require_finite(
                iso_level,
                name="iso_level",
            )
        )

        result = bytearray(
            self.sample_count
        )

        for (
            index,
            value,
        ) in enumerate(
            self.values
        ):
            result[
                index
            ] = (
                1
                if float(
                    value
                )
                <= resolved_iso
                else 0
            )

        return bytes(
            result
        )

    # -----------------------------------------------------
    # Trilinear normalized sampling
    # -----------------------------------------------------

    def sample_normalized(
        self,
        x: float,
        y: float,
        z: float,
    ) -> float:
        """
        Trilinear sample in normalized reconstruction space.

            -1 -> first grid sample
            +1 -> last grid sample
        """

        x = _clamp(
            _require_finite(
                x,
                name="x",
            ),
            -1.0,
            1.0,
        )

        y = _clamp(
            _require_finite(
                y,
                name="y",
            ),
            -1.0,
            1.0,
        )

        z = _clamp(
            _require_finite(
                z,
                name="z",
            ),
            -1.0,
            1.0,
        )

        gx = (
            (
                x
                + 1.0
            )
            * 0.5
            * float(
                self.width - 1
            )
        )

        gy = (
            (
                y
                + 1.0
            )
            * 0.5
            * float(
                self.depth - 1
            )
        )

        gz = (
            (
                z
                + 1.0
            )
            * 0.5
            * float(
                self.height - 1
            )
        )

        x0 = int(
            math.floor(
                gx
            )
        )

        y0 = int(
            math.floor(
                gy
            )
        )

        z0 = int(
            math.floor(
                gz
            )
        )

        x1 = min(
            x0 + 1,
            self.width - 1,
        )

        y1 = min(
            y0 + 1,
            self.depth - 1,
        )

        z1 = min(
            z0 + 1,
            self.height - 1,
        )

        tx = (
            gx
            - float(
                x0
            )
        )

        ty = (
            gy
            - float(
                y0
            )
        )

        tz = (
            gz
            - float(
                z0
            )
        )

        c000 = self.get(
            x0,
            y0,
            z0,
        )

        c100 = self.get(
            x1,
            y0,
            z0,
        )

        c010 = self.get(
            x0,
            y1,
            z0,
        )

        c110 = self.get(
            x1,
            y1,
            z0,
        )

        c001 = self.get(
            x0,
            y0,
            z1,
        )

        c101 = self.get(
            x1,
            y0,
            z1,
        )

        c011 = self.get(
            x0,
            y1,
            z1,
        )

        c111 = self.get(
            x1,
            y1,
            z1,
        )

        x00 = _lerp(
            c000,
            c100,
            tx,
        )

        x10 = _lerp(
            c010,
            c110,
            tx,
        )

        x01 = _lerp(
            c001,
            c101,
            tx,
        )

        x11 = _lerp(
            c011,
            c111,
            tx,
        )

        y0_value = _lerp(
            x00,
            x10,
            ty,
        )

        y1_value = _lerp(
            x01,
            x11,
            ty,
        )

        return _lerp(
            y0_value,
            y1_value,
            tz,
        )

    # -----------------------------------------------------
    # Surface cell test
    # -----------------------------------------------------

    def cell_crosses_surface(
        self,
        x: int,
        y: int,
        z: int,
        *,
        iso_level: float | None = None,
    ) -> bool:
        if (
            x < 0
            or x >= self.width - 1
            or y < 0
            or y >= self.depth - 1
            or z < 0
            or z >= self.height - 1
        ):
            raise IndexError(
                (
                    "SDF cell coordinate "
                    "outside bounds."
                )
            )

        iso = (
            self.iso_level
            if iso_level is None
            else _require_finite(
                iso_level,
                name="iso_level",
            )
        )

        values = (
            self.get(
                x,
                y,
                z,
            ),
            self.get(
                x + 1,
                y,
                z,
            ),
            self.get(
                x,
                y + 1,
                z,
            ),
            self.get(
                x + 1,
                y + 1,
                z,
            ),
            self.get(
                x,
                y,
                z + 1,
            ),
            self.get(
                x + 1,
                y,
                z + 1,
            ),
            self.get(
                x,
                y + 1,
                z + 1,
            ),
            self.get(
                x + 1,
                y + 1,
                z + 1,
            ),
        )

        minimum = min(
            values
        )

        maximum = max(
            values
        )

        return (
            minimum
            <= iso
            <= maximum
            and minimum
            < maximum
        )


# =========================================================
# Build configuration
# =========================================================

@dataclass(frozen=True)
class SDFBuildConfig:
    """
    Pure-Python SDF reference configuration.

    Width/depth/height describe scalar SAMPLE counts.

    Later the native implementation must preserve these exact
    sampling semantics.
    """

    width: int

    depth: int

    height: int

    symmetry_x: bool = (
        DEFAULT_SYMMETRY_X
    )

    smoothness: float = (
        DEFAULT_SMOOTHNESS
    )

    surface_offset: float = (
        DEFAULT_SURFACE_OFFSET
    )

    iso_level: float = (
        DEFAULT_ISO_LEVEL
    )

    max_voxels: int = (
        DEFAULT_REFERENCE_MAX_VOXELS
    )

    def validate(
        self,
    ) -> None:
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
                or value < 2
            ):
                raise ValueError(
                    (
                        f"{name} must be an "
                        "integer >= 2."
                    )
                )

        smoothness = (
            _require_finite(
                self.smoothness,
                name="smoothness",
            )
        )

        if smoothness < 0.0:
            raise ValueError(
                (
                    "smoothness cannot "
                    "be negative."
                )
            )

        _require_finite(
            self.surface_offset,
            name="surface_offset",
        )

        _require_finite(
            self.iso_level,
            name="iso_level",
        )

        if (
            not isinstance(
                self.max_voxels,
                int,
            )
            or isinstance(
                self.max_voxels,
                bool,
            )
            or self.max_voxels <= 0
        ):
            raise ValueError(
                (
                    "max_voxels must be a "
                    "positive integer."
                )
            )

        if (
            self.voxel_count
            > self.max_voxels
        ):
            raise ValueError(
                (
                    "Requested pure-Python SDF "
                    "volume is too large: "
                    f"{self.voxel_count} samples, "
                    f"limit {self.max_voxels}. "
                    "Use the future native SDF "
                    "backend for production-sized fields."
                )
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


def cubic_sdf_config(
    resolution: int,
    *,
    symmetry_x: bool = (
        DEFAULT_SYMMETRY_X
    ),
    smoothness: float = (
        DEFAULT_SMOOTHNESS
    ),
    surface_offset: float = (
        DEFAULT_SURFACE_OFFSET
    ),
    iso_level: float = (
        DEFAULT_ISO_LEVEL
    ),
    max_voxels: int = (
        DEFAULT_REFERENCE_MAX_VOXELS
    ),
) -> SDFBuildConfig:
    config = SDFBuildConfig(
        width=int(
            resolution
        ),
        depth=int(
            resolution
        ),
        height=int(
            resolution
        ),
        symmetry_x=bool(
            symmetry_x
        ),
        smoothness=float(
            smoothness
        ),
        surface_offset=float(
            surface_offset
        ),
        iso_level=float(
            iso_level
        ),
        max_voxels=int(
            max_voxels
        ),
    )

    config.validate()

    return config


# =========================================================
# Progress / result
# =========================================================

@dataclass(frozen=True)
class SDFBuildProgress:
    completed_slices: int

    total_slices: int

    @property
    def fraction(
        self,
    ) -> float:
        if self.total_slices <= 0:
            return 1.0

        return (
            float(
                self.completed_slices
            )
            / float(
                self.total_slices
            )
        )


@dataclass(frozen=True)
class SDFBuildStats:
    projection_count: int

    voxel_count: int

    projection_sample_count: int

    negative_samples: int

    zero_samples: int

    positive_samples: int

    minimum_distance: float

    maximum_distance: float

    symmetry_x: bool

    smoothness: float

    surface_offset: float

    iso_level: float

    @property
    def inside_samples(
        self,
    ) -> int:
        return (
            self.negative_samples
            + self.zero_samples
        )

    @property
    def outside_samples(
        self,
    ) -> int:
        return (
            self.positive_samples
        )

    @property
    def inside_ratio(
        self,
    ) -> float:
        if self.voxel_count <= 0:
            return 0.0

        return (
            float(
                self.inside_samples
            )
            / float(
                self.voxel_count
            )
        )


@dataclass(frozen=True)
class SDFBuildResult:
    volume: SDFVolume

    stats: SDFBuildStats

    projections: tuple[
        SDFProjection,
        ...
    ]

    config: SDFBuildConfig


# =========================================================
# Build dense 3D SDF
# =========================================================

def build_sdf_volume(
    projections: Sequence[
        SDFProjection
    ],
    *,
    config: SDFBuildConfig,
    progress_callback: (
        Callable[
            [
                SDFBuildProgress
            ],
            None,
        ]
        | None
    ) = None,
) -> SDFBuildResult:
    """
    Build the deterministic pure-Python reference field.

    Pipeline:

        silhouette
            ↓
        exact 2D signed distance
            ↓
        orthographic projection prism
            ↓
        max / smooth-max intersection
            ↓
        dense 3D signed scalar field

    This function intentionally prioritizes correctness and
    testability over production performance.
    """

    if not isinstance(
        config,
        SDFBuildConfig,
    ):
        raise TypeError(
            (
                "config must be "
                "SDFBuildConfig."
            )
        )

    config.validate()

    resolved_projections = tuple(
        projections
    )

    if not resolved_projections:
        raise ValueError(
            (
                "At least one SDF projection "
                "is required."
            )
        )

    for projection in (
        resolved_projections
    ):
        if not isinstance(
            projection,
            SDFProjection,
        ):
            raise TypeError(
                (
                    "All projections must be "
                    "SDFProjection instances."
                )
            )

    if (
        progress_callback
        is not None
        and not callable(
            progress_callback
        )
    ):
        raise TypeError(
            (
                "progress_callback must "
                "be callable."
            )
        )

    width = (
        config.width
    )

    depth = (
        config.depth
    )

    height = (
        config.height
    )

    voxel_count = (
        config.voxel_count
    )

    values = array(
        "f",
        [
            0.0
        ],
    ) * voxel_count

    normalized_x = tuple(
        grid_to_normalized(
            index,
            width,
        )
        for index
        in range(
            width
        )
    )

    normalized_y = tuple(
        grid_to_normalized(
            index,
            depth,
        )
        for index
        in range(
            depth
        )
    )

    normalized_z = tuple(
        grid_to_normalized(
            index,
            height,
        )
        for index
        in range(
            height
        )
    )

    negative_samples = 0

    zero_samples = 0

    positive_samples = 0

    minimum_distance = (
        math.inf
    )

    maximum_distance = (
        -math.inf
    )

    target_index = 0

    for (
        z_index,
        nz,
    ) in enumerate(
        normalized_z
    ):
        for ny in (
            normalized_y
        ):
            for nx in (
                normalized_x
            ):
                point = NormalizedPoint(
                    x=nx,
                    y=ny,
                    z=nz,
                )

                value = sample_fused_sdf(
                    point,
                    resolved_projections,
                    symmetry_x=(
                        config
                        .symmetry_x
                    ),
                    smoothness=(
                        config
                        .smoothness
                    ),
                    surface_offset=(
                        config
                        .surface_offset
                    ),
                )

                # iso_level is a downstream extraction
                # threshold. We store the actual fused field,
                # rather than baking the iso into each sample.

                values[
                    target_index
                ] = float(
                    value
                )

                target_index += 1

                minimum_distance = min(
                    minimum_distance,
                    value,
                )

                maximum_distance = max(
                    maximum_distance,
                    value,
                )

                relative = (
                    value
                    - config.iso_level
                )

                if (
                    relative
                    < -SIGN_EPSILON
                ):
                    negative_samples += 1

                elif (
                    relative
                    > SIGN_EPSILON
                ):
                    positive_samples += 1

                else:
                    zero_samples += 1

        if progress_callback is not None:
            progress_callback(
                SDFBuildProgress(
                    completed_slices=(
                        z_index
                        + 1
                    ),
                    total_slices=(
                        height
                    ),
                )
            )

    projection_sample_count = (
        voxel_count
        * len(
            resolved_projections
        )
        * (
            2
            if config.symmetry_x
            else 1
        )
    )

    volume = SDFVolume(
        width=width,
        depth=depth,
        height=height,
        values=values,
        iso_level=(
            config.iso_level
        ),
    )

    stats = SDFBuildStats(
        projection_count=len(
            resolved_projections
        ),

        voxel_count=(
            voxel_count
        ),

        projection_sample_count=(
            projection_sample_count
        ),

        negative_samples=(
            negative_samples
        ),

        zero_samples=(
            zero_samples
        ),

        positive_samples=(
            positive_samples
        ),

        minimum_distance=float(
            minimum_distance
        ),

        maximum_distance=float(
            maximum_distance
        ),

        symmetry_x=(
            config.symmetry_x
        ),

        smoothness=(
            config.smoothness
        ),

        surface_offset=(
            config.surface_offset
        ),

        iso_level=(
            config.iso_level
        ),
    )

    return SDFBuildResult(
        volume=volume,
        stats=stats,
        projections=(
            resolved_projections
        ),
        config=config,
    )


# =========================================================
# Convenience entry point
# =========================================================

def build_sdf_from_views(
    views: Iterable[
        Any
    ],
    *,
    config: SDFBuildConfig,
    progress_callback: (
        Callable[
            [
                SDFBuildProgress
            ],
            None,
        ]
        | None
    ) = None,
) -> SDFBuildResult:
    """
    Convenience bridge from INPUT prepared views.

    This function deliberately uses capabilities instead of
    importing ProjectionImagesOutput.
    """

    projections = (
        build_sdf_projections(
            views
        )
    )

    return build_sdf_volume(
        projections,
        config=config,
        progress_callback=(
            progress_callback
        ),
    )


# =========================================================
# Public API
# =========================================================

__all__ = (
    "DEFAULT_ISO_LEVEL",
    "DEFAULT_REFERENCE_MAX_VOXELS",
    "DEFAULT_SMOOTHNESS",
    "DEFAULT_SURFACE_OFFSET",
    "DEFAULT_SYMMETRY_X",
    "SDFBuildConfig",
    "SDFBuildProgress",
    "SDFBuildResult",
    "SDFBuildStats",
    "SDFProjection",
    "SDFVolume",
    "SIGN_EPSILON",
    "SignedDistanceMask",
    "build_sdf_from_views",
    "build_sdf_projections",
    "build_sdf_volume",
    "build_signed_distance_mask",
    "cubic_sdf_config",
    "fuse_signed_distances",
    "sample_fused_sdf",
    "smooth_max",
)