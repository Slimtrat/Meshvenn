from __future__ import annotations

import math

from array import array
from dataclasses import (
    dataclass,
    field,
)
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    Sequence,
    TypeAlias,
)


# =========================================================
# Types
# =========================================================

Vector2: TypeAlias = tuple[
    float,
    float,
]

Vector3: TypeAlias = tuple[
    float,
    float,
    float,
]

RGBA: TypeAlias = tuple[
    float,
    float,
    float,
    float,
]


# =========================================================
# Constants
# =========================================================

DEFAULT_TEXTURE_SIZE = 1024

DEFAULT_PADDING_PIXELS = 8

DEFAULT_SAMPLES_PER_AXIS = 1

DEFAULT_BACKGROUND_COLOR: RGBA = (
    0.0,
    0.0,
    0.0,
    0.0,
)

DEFAULT_BARYCENTRIC_EPSILON = 1e-8

DEFAULT_DEGENERATE_UV_EPSILON = 1e-12

MAX_TEXTURE_DIMENSION = 4096

MAX_PADDING_PIXELS = 128

MAX_SAMPLES_PER_AXIS = 4

NORMAL_EPSILON = 1e-12

COLOR_CHANNEL_COUNT = 4

UNVISITED_DISTANCE = 65535


# =========================================================
# Small helpers
# =========================================================

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


def _finite_float(
    value: Any,
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
            f"{name} must be finite."
        )

    return result


def _vector2(
    value: Sequence[
        float
    ],
    *,
    name: str,
) -> Vector2:
    if len(value) != 2:
        raise ValueError(
            (
                f"{name} must contain "
                "exactly 2 values."
            )
        )

    return (
        _finite_float(
            value[0],
            name=f"{name}.x",
        ),
        _finite_float(
            value[1],
            name=f"{name}.y",
        ),
    )


def _vector3(
    value: Sequence[
        float
    ],
    *,
    name: str,
) -> Vector3:
    if len(value) != 3:
        raise ValueError(
            (
                f"{name} must contain "
                "exactly 3 values."
            )
        )

    return (
        _finite_float(
            value[0],
            name=f"{name}.x",
        ),
        _finite_float(
            value[1],
            name=f"{name}.y",
        ),
        _finite_float(
            value[2],
            name=f"{name}.z",
        ),
    )


def _rgba(
    value: Sequence[
        float
    ],
    *,
    name: str,
    clamp: bool,
) -> RGBA:
    if len(value) != 4:
        raise ValueError(
            (
                f"{name} must contain "
                "exactly 4 values."
            )
        )

    channels = tuple(
        _finite_float(
            channel,
            name=(
                f"{name}[{index}]"
            ),
        )
        for (
            index,
            channel,
        ) in enumerate(
            value
        )
    )

    if clamp:
        return (
            clamp01(
                channels[0]
            ),
            clamp01(
                channels[1]
            ),
            clamp01(
                channels[2]
            ),
            clamp01(
                channels[3]
            ),
        )

    return (
        channels[0],
        channels[1],
        channels[2],
        channels[3],
    )


# =========================================================
# Vector math
# =========================================================

def _length3(
    value: Vector3,
) -> float:
    return math.sqrt(
        value[0]
        * value[0]
        + value[1]
        * value[1]
        + value[2]
        * value[2]
    )


def _normalize3(
    value: Vector3,
) -> Vector3:
    length = _length3(
        value
    )

    if (
        not math.isfinite(
            length
        )
        or length
        <= NORMAL_EPSILON
    ):
        raise ValueError(
            (
                "Surface normal must be "
                "a finite non-zero vector."
            )
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


def _cross3(
    a: Vector3,
    b: Vector3,
) -> Vector3:
    return (
        a[1] * b[2]
        - a[2] * b[1],

        a[2] * b[0]
        - a[0] * b[2],

        a[0] * b[1]
        - a[1] * b[0],
    )


def _subtract3(
    a: Vector3,
    b: Vector3,
) -> Vector3:
    return (
        a[0] - b[0],
        a[1] - b[1],
        a[2] - b[2],
    )


def _interpolate3(
    a: Vector3,
    b: Vector3,
    c: Vector3,
    weights: tuple[
        float,
        float,
        float,
    ],
) -> Vector3:
    (
        wa,
        wb,
        wc,
    ) = weights

    return (
        a[0] * wa
        + b[0] * wb
        + c[0] * wc,

        a[1] * wa
        + b[1] * wb
        + c[1] * wc,

        a[2] * wa
        + b[2] * wb
        + c[2] * wc,
    )


# =========================================================
# Bake vertex
# =========================================================

@dataclass(frozen=True)
class UVBakeVertex:
    """
    One corner of a triangle participating in texture bake.

    position:
        Mesh-local surface position.

    normal:
        Mesh-local surface normal.

    uv:
        UV coordinates.

        Convention:

            u = 0 -> left
            u = 1 -> right

            v = 0 -> bottom
            v = 1 -> top

    The convention deliberately matches Blender image pixel
    storage and Meshvenn's projection system.
    """

    position: Vector3

    normal: Vector3

    uv: Vector2

    def __post_init__(
        self,
    ) -> None:
        position = _vector3(
            self.position,
            name="position",
        )

        normal = _normalize3(
            _vector3(
                self.normal,
                name="normal",
            )
        )

        uv = _vector2(
            self.uv,
            name="uv",
        )

        object.__setattr__(
            self,
            "position",
            position,
        )

        object.__setattr__(
            self,
            "normal",
            normal,
        )

        object.__setattr__(
            self,
            "uv",
            uv,
        )


# =========================================================
# Bake triangle
# =========================================================

@dataclass(frozen=True)
class UVBakeTriangle:
    """
    One UV-space triangle.

    Blender-specific triangulation belongs to the adapter.

    The core only needs three corners containing:

        position
        normal
        uv
    """

    a: UVBakeVertex

    b: UVBakeVertex

    c: UVBakeVertex

    source_index: int = -1

    @property
    def signed_uv_area_twice(
        self,
    ) -> float:
        ax, ay = (
            self.a.uv
        )

        bx, by = (
            self.b.uv
        )

        cx, cy = (
            self.c.uv
        )

        return (
            (
                bx - ax
            )
            * (
                cy - ay
            )
            - (
                by - ay
            )
            * (
                cx - ax
            )
        )

    @property
    def absolute_uv_area(
        self,
    ) -> float:
        return (
            abs(
                self
                .signed_uv_area_twice
            )
            * 0.5
        )

    @property
    def has_uv_outside_unit_square(
        self,
    ) -> bool:
        for vertex in (
            self.a,
            self.b,
            self.c,
        ):
            (
                u,
                v,
            ) = (
                vertex.uv
            )

            if (
                u < 0.0
                or u > 1.0
                or v < 0.0
                or v > 1.0
            ):
                return True

        return False


# =========================================================
# Surface color sample
# =========================================================

@dataclass(frozen=True)
class SurfaceColorSample:
    """
    Color returned by the surface sampler.

    UV bake deliberately knows nothing about how this color
    was obtained.

    Current adapter:

        position + normal
            ↓
        Projected Color V1.2
            ↓
        SurfaceColorSample

    Future possibilities:

        vertex paint
        procedural material
        neural appearance
        photogrammetry texture
    """

    color: RGBA

    used_fallback: bool = False

    selected_samples: int = 0

    metadata: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "color",
            _rgba(
                self.color,
                name="color",
                clamp=False,
            ),
        )

        selected_samples = int(
            self.selected_samples
        )

        if selected_samples < 0:
            raise ValueError(
                (
                    "selected_samples "
                    "cannot be negative."
                )
            )

        object.__setattr__(
            self,
            "selected_samples",
            selected_samples,
        )


SurfaceColorSampler: TypeAlias = Callable[
    [
        Vector3,
        Vector3,
    ],
    (
        SurfaceColorSample
        | RGBA
    ),
]


# =========================================================
# Bake configuration
# =========================================================

@dataclass(frozen=True)
class UVBakeConfig:
    """
    Generic UV texture bake configuration.

    width / height:
        Texture resolution.

    padding_pixels:
        Number of texels dilated around baked UV islands.

        Padding is important because bilinear filtering and
        mipmaps sample slightly outside UV island borders.

    samples_per_axis:
        1 -> 1 sample / texel
        2 -> 4 samples / texel
        3 -> 9 samples / texel
        4 -> 16 samples / texel

        Default intentionally remains 1 because projected
        color may perform visibility raycasts for every
        sample.

    background_color:
        Color of texels not occupied by an island or padding.

    clamp_colors:
        Clamp sampled RGBA into [0, 1].

    barycentric_epsilon:
        Numerical tolerance used when classifying samples on
        triangle edges.

    degenerate_uv_epsilon:
        Minimum absolute twice-area of a rasterizable UV
        triangle.
    """

    width: int = (
        DEFAULT_TEXTURE_SIZE
    )

    height: int = (
        DEFAULT_TEXTURE_SIZE
    )

    padding_pixels: int = (
        DEFAULT_PADDING_PIXELS
    )

    samples_per_axis: int = (
        DEFAULT_SAMPLES_PER_AXIS
    )

    background_color: RGBA = (
        DEFAULT_BACKGROUND_COLOR
    )

    clamp_colors: bool = True

    barycentric_epsilon: float = (
        DEFAULT_BARYCENTRIC_EPSILON
    )

    degenerate_uv_epsilon: float = (
        DEFAULT_DEGENERATE_UV_EPSILON
    )

    def validate(
        self,
    ) -> None:
        if (
            not isinstance(
                self.width,
                int,
            )
            or self.width <= 0
            or self.width
            > MAX_TEXTURE_DIMENSION
        ):
            raise ValueError(
                (
                    "Texture width must be "
                    f"between 1 and "
                    f"{MAX_TEXTURE_DIMENSION}."
                )
            )

        if (
            not isinstance(
                self.height,
                int,
            )
            or self.height <= 0
            or self.height
            > MAX_TEXTURE_DIMENSION
        ):
            raise ValueError(
                (
                    "Texture height must be "
                    f"between 1 and "
                    f"{MAX_TEXTURE_DIMENSION}."
                )
            )

        if (
            not isinstance(
                self.padding_pixels,
                int,
            )
            or self.padding_pixels < 0
            or self.padding_pixels
            > MAX_PADDING_PIXELS
        ):
            raise ValueError(
                (
                    "padding_pixels must be "
                    f"between 0 and "
                    f"{MAX_PADDING_PIXELS}."
                )
            )

        if (
            not isinstance(
                self.samples_per_axis,
                int,
            )
            or self.samples_per_axis < 1
            or self.samples_per_axis
            > MAX_SAMPLES_PER_AXIS
        ):
            raise ValueError(
                (
                    "samples_per_axis must be "
                    f"between 1 and "
                    f"{MAX_SAMPLES_PER_AXIS}."
                )
            )

        barycentric_epsilon = (
            _finite_float(
                self.barycentric_epsilon,
                name=(
                    "barycentric_epsilon"
                ),
            )
        )

        if barycentric_epsilon < 0.0:
            raise ValueError(
                (
                    "barycentric_epsilon "
                    "cannot be negative."
                )
            )

        degenerate_epsilon = (
            _finite_float(
                self.degenerate_uv_epsilon,
                name=(
                    "degenerate_uv_epsilon"
                ),
            )
        )

        if degenerate_epsilon <= 0.0:
            raise ValueError(
                (
                    "degenerate_uv_epsilon "
                    "must be greater than zero."
                )
            )

        _rgba(
            self.background_color,
            name="background_color",
            clamp=(
                self.clamp_colors
            ),
        )


# =========================================================
# Texture buffer
# =========================================================

@dataclass
class TextureBuffer:
    """
    Bottom-left-origin floating point RGBA texture.

    Pixel index:

        ((y * width) + x) * 4

    This intentionally matches Blender image.pixels.
    """

    width: int

    height: int

    pixels: array

    def __post_init__(
        self,
    ) -> None:
        if (
            self.width <= 0
            or self.height <= 0
        ):
            raise ValueError(
                (
                    "Texture dimensions "
                    "must be positive."
                )
            )

        expected = (
            self.width
            * self.height
            * COLOR_CHANNEL_COUNT
        )

        if len(
            self.pixels
        ) != expected:
            raise ValueError(
                (
                    "Texture pixel buffer "
                    "length mismatch. "
                    f"Expected {expected}, "
                    f"received "
                    f"{len(self.pixels)}."
                )
            )

    @classmethod
    def filled(
        cls,
        width: int,
        height: int,
        color: RGBA,
    ) -> "TextureBuffer":
        pixel_count = (
            int(
                width
            )
            * int(
                height
            )
        )

        pixels = array(
            "f",
        )

        pixels.extend(
            color
            * pixel_count
        )

        return cls(
            width=int(
                width
            ),
            height=int(
                height
            ),
            pixels=pixels,
        )

    @property
    def pixel_count(
        self,
    ) -> int:
        return (
            self.width
            * self.height
        )

    def _offset(
        self,
        x: int,
        y: int,
    ) -> int:
        if (
            x < 0
            or x >= self.width
            or y < 0
            or y >= self.height
        ):
            raise IndexError(
                (
                    "Texture coordinates "
                    f"outside image: "
                    f"({x}, {y})."
                )
            )

        return (
            (
                y
                * self.width
                + x
            )
            * COLOR_CHANNEL_COUNT
        )

    def rgba(
        self,
        x: int,
        y: int,
    ) -> RGBA:
        offset = (
            self._offset(
                x,
                y,
            )
        )

        return (
            float(
                self.pixels[
                    offset
                ]
            ),
            float(
                self.pixels[
                    offset + 1
                ]
            ),
            float(
                self.pixels[
                    offset + 2
                ]
            ),
            float(
                self.pixels[
                    offset + 3
                ]
            ),
        )

    def set_rgba(
        self,
        x: int,
        y: int,
        color: RGBA,
    ) -> None:
        offset = (
            self._offset(
                x,
                y,
            )
        )

        self.pixels[
            offset
        ] = color[0]

        self.pixels[
            offset + 1
        ] = color[1]

        self.pixels[
            offset + 2
        ] = color[2]

        self.pixels[
            offset + 3
        ] = color[3]

    def copy_pixel(
        self,
        source_index: int,
        destination_index: int,
    ) -> None:
        source_offset = (
            source_index
            * COLOR_CHANNEL_COUNT
        )

        destination_offset = (
            destination_index
            * COLOR_CHANNEL_COUNT
        )

        for channel in range(
            COLOR_CHANNEL_COUNT
        ):
            self.pixels[
                destination_offset
                + channel
            ] = (
                self.pixels[
                    source_offset
                    + channel
                ]
            )


# =========================================================
# Statistics
# =========================================================

@dataclass(frozen=True)
class UVBakeStats:
    triangle_count: int

    rasterized_triangles: int

    degenerate_triangles: int

    clipped_triangles: int

    outside_triangles: int

    covered_pixels: int

    padded_pixels: int

    overlap_pixels: int

    surface_samples: int

    fallback_samples: int

    selected_source_samples: int

    texture_width: int

    texture_height: int

    samples_per_axis: int

    padding_pixels: int

    @property
    def texture_pixels(
        self,
    ) -> int:
        return (
            self.texture_width
            * self.texture_height
        )

    @property
    def filled_pixels(
        self,
    ) -> int:
        return (
            self.covered_pixels
            + self.padded_pixels
        )

    @property
    def uncovered_pixels(
        self,
    ) -> int:
        return max(
            0,
            self.texture_pixels
            - self.filled_pixels,
        )

    @property
    def coverage_ratio(
        self,
    ) -> float:
        if self.texture_pixels <= 0:
            return 0.0

        return (
            float(
                self.covered_pixels
            )
            / float(
                self.texture_pixels
            )
        )


# =========================================================
# Result
# =========================================================

@dataclass(frozen=True)
class UVBakeResult:
    texture: TextureBuffer

    stats: UVBakeStats

    # Original rasterized island pixels.
    coverage: bytes

    # Coverage + texture padding.
    filled: bytes

    def is_covered(
        self,
        x: int,
        y: int,
    ) -> bool:
        index = (
            y
            * self.texture.width
            + x
        )

        return bool(
            self.coverage[
                index
            ]
        )

    def is_filled(
        self,
        x: int,
        y: int,
    ) -> bool:
        index = (
            y
            * self.texture.width
            + x
        )

        return bool(
            self.filled[
                index
            ]
        )


# =========================================================
# Progress
# =========================================================

@dataclass(frozen=True)
class UVBakeProgress:
    completed_triangles: int

    total_triangles: int

    @property
    def fraction(
        self,
    ) -> float:
        if self.total_triangles <= 0:
            return 1.0

        return clamp01(
            float(
                self.completed_triangles
            )
            / float(
                self.total_triangles
            )
        )


UVBakeProgressCallback: TypeAlias = Callable[
    [
        UVBakeProgress
    ],
    None,
]


# =========================================================
# Internal raster statistics
# =========================================================

@dataclass
class _MutableBakeStats:
    rasterized_triangles: int = 0

    degenerate_triangles: int = 0

    clipped_triangles: int = 0

    outside_triangles: int = 0

    overlap_pixels: int = 0

    surface_samples: int = 0

    fallback_samples: int = 0

    selected_source_samples: int = 0


# =========================================================
# Surface sample conversion
# =========================================================

def _coerce_surface_sample(
    value: (
        SurfaceColorSample
        | Sequence[
            float
        ]
    ),
    *,
    clamp_colors: bool,
) -> SurfaceColorSample:
    if isinstance(
        value,
        SurfaceColorSample,
    ):
        color = _rgba(
            value.color,
            name="surface sample color",
            clamp=clamp_colors,
        )

        if color == value.color:
            return value

        return SurfaceColorSample(
            color=color,
            used_fallback=(
                value.used_fallback
            ),
            selected_samples=(
                value.selected_samples
            ),
            metadata=(
                value.metadata
            ),
        )

    color = _rgba(
        value,
        name="surface sample",
        clamp=clamp_colors,
    )

    return SurfaceColorSample(
        color=color
    )


# =========================================================
# Barycentric coordinates
# =========================================================

def _barycentric_weights(
    point: Vector2,
    triangle: UVBakeTriangle,
    *,
    epsilon: float,
) -> (
    tuple[
        float,
        float,
        float,
    ]
    | None
):
    (
        px,
        py,
    ) = point

    (
        ax,
        ay,
    ) = (
        triangle.a.uv
    )

    (
        bx,
        by,
    ) = (
        triangle.b.uv
    )

    (
        cx,
        cy,
    ) = (
        triangle.c.uv
    )

    denominator = (
        (
            by - cy
        )
        * (
            ax - cx
        )
        + (
            cx - bx
        )
        * (
            ay - cy
        )
    )

    if (
        not math.isfinite(
            denominator
        )
        or abs(
            denominator
        )
        <= DEFAULT_DEGENERATE_UV_EPSILON
    ):
        return None

    wa = (
        (
            (
                by - cy
            )
            * (
                px - cx
            )
            + (
                cx - bx
            )
            * (
                py - cy
            )
        )
        / denominator
    )

    wb = (
        (
            (
                cy - ay
            )
            * (
                px - cx
            )
            + (
                ax - cx
            )
            * (
                py - cy
            )
        )
        / denominator
    )

    wc = (
        1.0
        - wa
        - wb
    )

    if (
        wa < -epsilon
        or wb < -epsilon
        or wc < -epsilon
    ):
        return None

    return (
        wa,
        wb,
        wc,
    )


def _interior_score(
    weights: tuple[
        float,
        float,
        float,
    ],
) -> float:
    """
    Larger means further inside the triangle.

    This is used when two UV triangles touch/overlap the same
    texel.

    Choosing the most interior candidate is more stable than
    blindly allowing whichever triangle happened to be
    rasterized last.
    """

    return max(
        0.0,
        min(
            weights
        ),
    )


# =========================================================
# Triangle surface interpolation
# =========================================================

def _face_normal(
    triangle: UVBakeTriangle,
) -> Vector3:
    edge_ab = (
        _subtract3(
            triangle.b.position,
            triangle.a.position,
        )
    )

    edge_ac = (
        _subtract3(
            triangle.c.position,
            triangle.a.position,
        )
    )

    return _normalize3(
        _cross3(
            edge_ab,
            edge_ac,
        )
    )


def _surface_point(
    triangle: UVBakeTriangle,
    weights: tuple[
        float,
        float,
        float,
    ],
) -> tuple[
    Vector3,
    Vector3,
]:
    position = (
        _interpolate3(
            triangle.a.position,
            triangle.b.position,
            triangle.c.position,
            weights,
        )
    )

    interpolated_normal = (
        _interpolate3(
            triangle.a.normal,
            triangle.b.normal,
            triangle.c.normal,
            weights,
        )
    )

    try:
        normal = (
            _normalize3(
                interpolated_normal
            )
        )

    except ValueError:
        normal = (
            _face_normal(
                triangle
            )
        )

    return (
        position,
        normal,
    )


# =========================================================
# Pixel-space bounds
# =========================================================

def _triangle_pixel_bounds(
    triangle: UVBakeTriangle,
    *,
    width: int,
    height: int,
) -> (
    tuple[
        int,
        int,
        int,
        int,
    ]
    | None
):
    u_values = (
        triangle.a.uv[0],
        triangle.b.uv[0],
        triangle.c.uv[0],
    )

    v_values = (
        triangle.a.uv[1],
        triangle.b.uv[1],
        triangle.c.uv[1],
    )

    minimum_u = min(
        u_values
    )

    maximum_u = max(
        u_values
    )

    minimum_v = min(
        v_values
    )

    maximum_v = max(
        v_values
    )

    if (
        maximum_u < 0.0
        or minimum_u > 1.0
        or maximum_v < 0.0
        or minimum_v > 1.0
    ):
        return None

    minimum_x = max(
        0,
        int(
            math.floor(
                minimum_u
                * width
            )
        ),
    )

    maximum_x = min(
        width - 1,
        int(
            math.ceil(
                maximum_u
                * width
            )
            - 1
        ),
    )

    minimum_y = max(
        0,
        int(
            math.floor(
                minimum_v
                * height
            )
        ),
    )

    maximum_y = min(
        height - 1,
        int(
            math.ceil(
                maximum_v
                * height
            )
            - 1
        ),
    )

    if (
        minimum_x > maximum_x
        or minimum_y > maximum_y
    ):
        return None

    return (
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    )


# =========================================================
# Subsample locations
# =========================================================

def _subsample_offsets(
    samples_per_axis: int,
) -> tuple[
    float,
    ...
]:
    inverse = (
        1.0
        / float(
            samples_per_axis
        )
    )

    return tuple(
        (
            float(
                index
            )
            + 0.5
        )
        * inverse
        for index
        in range(
            samples_per_axis
        )
    )


# =========================================================
# Triangle rasterization
# =========================================================

def _rasterize_triangle(
    triangle: UVBakeTriangle,
    *,
    texture: TextureBuffer,
    coverage: bytearray,
    ownership_scores: array,
    overlap_mask: bytearray,
    sampler: SurfaceColorSampler,
    config: UVBakeConfig,
    stats: _MutableBakeStats,
) -> bool:
    if (
        abs(
            triangle
            .signed_uv_area_twice
        )
        <= config
        .degenerate_uv_epsilon
    ):
        stats.degenerate_triangles += 1

        return False

    if (
        triangle
        .has_uv_outside_unit_square
    ):
        stats.clipped_triangles += 1

    bounds = (
        _triangle_pixel_bounds(
            triangle,
            width=(
                texture.width
            ),
            height=(
                texture.height
            ),
        )
    )

    if bounds is None:
        stats.outside_triangles += 1

        return False

    (
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    ) = bounds

    offsets = (
        _subsample_offsets(
            config.samples_per_axis
        )
    )

    triangle_wrote_pixel = False

    for y in range(
        minimum_y,
        maximum_y + 1,
    ):
        for x in range(
            minimum_x,
            maximum_x + 1,
        ):
            accumulated_red = 0.0

            accumulated_green = 0.0

            accumulated_blue = 0.0

            accumulated_alpha = 0.0

            accumulated_score = 0.0

            sample_count = 0

            fallback_count = 0

            selected_source_samples = 0

            for offset_y in (
                offsets
            ):
                v = (
                    (
                        float(
                            y
                        )
                        + offset_y
                    )
                    / float(
                        texture.height
                    )
                )

                for offset_x in (
                    offsets
                ):
                    u = (
                        (
                            float(
                                x
                            )
                            + offset_x
                        )
                        / float(
                            texture.width
                        )
                    )

                    weights = (
                        _barycentric_weights(
                            (
                                u,
                                v,
                            ),
                            triangle,
                            epsilon=(
                                config
                                .barycentric_epsilon
                            ),
                        )
                    )

                    if weights is None:
                        continue

                    (
                        position,
                        normal,
                    ) = (
                        _surface_point(
                            triangle,
                            weights,
                        )
                    )

                    sampled = (
                        _coerce_surface_sample(
                            sampler(
                                position,
                                normal,
                            ),
                            clamp_colors=(
                                config
                                .clamp_colors
                            ),
                        )
                    )

                    (
                        red,
                        green,
                        blue,
                        alpha,
                    ) = (
                        sampled.color
                    )

                    accumulated_red += (
                        red
                    )

                    accumulated_green += (
                        green
                    )

                    accumulated_blue += (
                        blue
                    )

                    accumulated_alpha += (
                        alpha
                    )

                    accumulated_score += (
                        _interior_score(
                            weights
                        )
                    )

                    sample_count += 1

                    if sampled.used_fallback:
                        fallback_count += 1

                    selected_source_samples += (
                        sampled
                        .selected_samples
                    )

            if sample_count == 0:
                continue

            inverse_sample_count = (
                1.0
                / float(
                    sample_count
                )
            )

            color = (
                accumulated_red
                * inverse_sample_count,

                accumulated_green
                * inverse_sample_count,

                accumulated_blue
                * inverse_sample_count,

                accumulated_alpha
                * inverse_sample_count,
            )

            score = (
                accumulated_score
                * inverse_sample_count
            )

            pixel_index = (
                y
                * texture.width
                + x
            )

            already_covered = bool(
                coverage[
                    pixel_index
                ]
            )

            if (
                already_covered
                and not overlap_mask[
                    pixel_index
                ]
            ):
                overlap_mask[
                    pixel_index
                ] = 1

                stats.overlap_pixels += 1

            # -------------------------------------------------
            # Resolve UV overlap.
            #
            # Prefer the triangle whose successful samples lie
            # further inside its UV area.
            #
            # Exact ties preserve the first triangle, keeping
            # output deterministic.
            # -------------------------------------------------

            previous_score = float(
                ownership_scores[
                    pixel_index
                ]
            )

            should_write = (
                not already_covered
                or score
                > previous_score
            )

            if should_write:
                texture.set_rgba(
                    x,
                    y,
                    color,
                )

                ownership_scores[
                    pixel_index
                ] = float(
                    score
                )

                coverage[
                    pixel_index
                ] = 1

                triangle_wrote_pixel = True

            # -------------------------------------------------
            # Sampling diagnostics describe actual work, even
            # when an overlapping triangle loses ownership.
            # -------------------------------------------------

            stats.surface_samples += (
                sample_count
            )

            stats.fallback_samples += (
                fallback_count
            )

            stats.selected_source_samples += (
                selected_source_samples
            )

    return (
        triangle_wrote_pixel
    )


# =========================================================
# Texture padding / dilation
# =========================================================

def _dilate_texture(
    texture: TextureBuffer,
    coverage: bytearray,
    *,
    padding_pixels: int,
) -> tuple[
    bytes,
    int,
]:
    """
    Expand baked colors around UV islands.

    The algorithm is a bounded multi-source breadth-first
    expansion.

    Every covered texel starts at distance 0.

    Neighbouring empty texels receive the nearest available
    baked color up to `padding_pixels` Manhattan distance.

    Coverage itself is NOT modified:

        coverage
            actual UV island

        filled
            UV island + padding
    """

    pixel_count = (
        texture.pixel_count
    )

    filled = bytearray(
        coverage
    )

    if (
        padding_pixels <= 0
        or pixel_count == 0
    ):
        return (
            bytes(
                filled
            ),
            0,
        )

    distances = (
        array(
            "H",
            [
                UNVISITED_DISTANCE
            ],
        )
        * pixel_count
    )

    queue = array(
        "I"
    )

    for pixel_index in range(
        pixel_count
    ):
        if not coverage[
            pixel_index
        ]:
            continue

        distances[
            pixel_index
        ] = 0

        queue.append(
            pixel_index
        )

    if not queue:
        return (
            bytes(
                filled
            ),
            0,
        )

    head = 0

    padded_pixels = 0

    width = (
        texture.width
    )

    height = (
        texture.height
    )

    last_row_start = (
        (
            height - 1
        )
        * width
    )

    while head < len(
        queue
    ):
        current = int(
            queue[
                head
            ]
        )

        head += 1

        current_distance = int(
            distances[
                current
            ]
        )

        if (
            current_distance
            >= padding_pixels
        ):
            continue

        next_distance = (
            current_distance
            + 1
        )

        x = (
            current
            % width
        )

        neighbours: list[
            int
        ] = []

        if x > 0:
            neighbours.append(
                current - 1
            )

        if x < (
            width - 1
        ):
            neighbours.append(
                current + 1
            )

        if current >= width:
            neighbours.append(
                current - width
            )

        if current < (
            last_row_start
        ):
            neighbours.append(
                current + width
            )

        for neighbour in (
            neighbours
        ):
            if (
                distances[
                    neighbour
                ]
                != UNVISITED_DISTANCE
            ):
                continue

            distances[
                neighbour
            ] = (
                next_distance
            )

            filled[
                neighbour
            ] = 1

            texture.copy_pixel(
                current,
                neighbour,
            )

            queue.append(
                neighbour
            )

            padded_pixels += 1

    return (
        bytes(
            filled
        ),
        padded_pixels,
    )


# =========================================================
# Public bake API
# =========================================================

def bake_uv_texture(
    triangles: Iterable[
        UVBakeTriangle
    ],
    sampler: SurfaceColorSampler,
    *,
    config: UVBakeConfig | None = None,
    progress_callback: (
        UVBakeProgressCallback
        | None
    ) = None,
) -> UVBakeResult:
    """
    Rasterize a UV mesh and evaluate one surface color
    function for every covered texture sample.

    Architecture:

        Blender mesh
            ↓ adapter
        UVBakeTriangle[]
            ↓
        core/uv_bake.py
            ↓
        position + normal
            ↓ sampler
        projected color / other appearance implementation
            ↓
        RGBA
            ↓
        rasterized texture
            ↓
        seam padding
            ↓
        UVBakeResult

    The core does NOT:

        - unwrap UVs;
        - know Blender;
        - create Blender images;
        - create materials;
        - save PNG files;
        - know visual hulls;
        - know projected material internals.

    Those responsibilities belong to implementations/.
    """

    if config is None:
        config = (
            UVBakeConfig()
        )

    config.validate()

    if not callable(
        sampler
    ):
        raise TypeError(
            "sampler must be callable."
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
                "progress_callback "
                "must be callable."
            )
        )

    triangle_list = tuple(
        triangles
    )

    if not triangle_list:
        raise ValueError(
            (
                "UV bake requires at least "
                "one triangle."
            )
        )

    for (
        index,
        triangle,
    ) in enumerate(
        triangle_list
    ):
        if not isinstance(
            triangle,
            UVBakeTriangle,
        ):
            raise TypeError(
                (
                    "triangles must contain "
                    "UVBakeTriangle values. "
                    f"Item {index} is "
                    f"{type(triangle).__name__}."
                )
            )

    background = (
        _rgba(
            config.background_color,
            name="background_color",
            clamp=(
                config.clamp_colors
            ),
        )
    )

    texture = (
        TextureBuffer.filled(
            config.width,
            config.height,
            background,
        )
    )

    pixel_count = (
        texture.pixel_count
    )

    coverage = bytearray(
        pixel_count
    )

    overlap_mask = bytearray(
        pixel_count
    )

    ownership_scores = (
        array(
            "f",
            [
                -1.0
            ],
        )
        * pixel_count
    )

    mutable_stats = (
        _MutableBakeStats()
    )

    total_triangles = len(
        triangle_list
    )

    for (
        triangle_index,
        triangle,
    ) in enumerate(
        triangle_list
    ):
        rasterized = (
            _rasterize_triangle(
                triangle,
                texture=texture,
                coverage=coverage,
                ownership_scores=(
                    ownership_scores
                ),
                overlap_mask=(
                    overlap_mask
                ),
                sampler=sampler,
                config=config,
                stats=(
                    mutable_stats
                ),
            )
        )

        if rasterized:
            mutable_stats.rasterized_triangles += 1

        if progress_callback is not None:
            progress_callback(
                UVBakeProgress(
                    completed_triangles=(
                        triangle_index
                        + 1
                    ),
                    total_triangles=(
                        total_triangles
                    ),
                )
            )

    covered_pixels = sum(
        coverage
    )

    (
        filled,
        padded_pixels,
    ) = (
        _dilate_texture(
            texture,
            coverage,
            padding_pixels=(
                config
                .padding_pixels
            ),
        )
    )

    stats = (
        UVBakeStats(
            triangle_count=(
                total_triangles
            ),
            rasterized_triangles=(
                mutable_stats
                .rasterized_triangles
            ),
            degenerate_triangles=(
                mutable_stats
                .degenerate_triangles
            ),
            clipped_triangles=(
                mutable_stats
                .clipped_triangles
            ),
            outside_triangles=(
                mutable_stats
                .outside_triangles
            ),
            covered_pixels=int(
                covered_pixels
            ),
            padded_pixels=(
                padded_pixels
            ),
            overlap_pixels=(
                mutable_stats
                .overlap_pixels
            ),
            surface_samples=(
                mutable_stats
                .surface_samples
            ),
            fallback_samples=(
                mutable_stats
                .fallback_samples
            ),
            selected_source_samples=(
                mutable_stats
                .selected_source_samples
            ),
            texture_width=(
                config.width
            ),
            texture_height=(
                config.height
            ),
            samples_per_axis=(
                config
                .samples_per_axis
            ),
            padding_pixels=(
                config
                .padding_pixels
            ),
        )
    )

    return (
        UVBakeResult(
            texture=texture,
            stats=stats,
            coverage=bytes(
                coverage
            ),
            filled=filled,
        )
    )


# =========================================================
# Convenience helpers
# =========================================================

def square_texture_config(
    size: int,
    *,
    padding_pixels: int = (
        DEFAULT_PADDING_PIXELS
    ),
    samples_per_axis: int = (
        DEFAULT_SAMPLES_PER_AXIS
    ),
    background_color: RGBA = (
        DEFAULT_BACKGROUND_COLOR
    ),
    clamp_colors: bool = True,
) -> UVBakeConfig:
    """
    Convenience constructor for the usual square texture
    workflow.
    """

    return UVBakeConfig(
        width=int(
            size
        ),
        height=int(
            size
        ),
        padding_pixels=int(
            padding_pixels
        ),
        samples_per_axis=int(
            samples_per_axis
        ),
        background_color=(
            background_color
        ),
        clamp_colors=bool(
            clamp_colors
        ),
    )


def texture_memory_bytes(
    width: int,
    height: int,
) -> int:
    """
    Approximate memory occupied by the RGBA float texture
    buffer itself.

    Does not include Python object overhead, coverage masks or
    temporary raster state.
    """

    normalized_width = int(
        width
    )

    normalized_height = int(
        height
    )

    if (
        normalized_width < 0
        or normalized_height < 0
    ):
        raise ValueError(
            (
                "Texture dimensions "
                "cannot be negative."
            )
        )

    return (
        normalized_width
        * normalized_height
        * COLOR_CHANNEL_COUNT
        * 4
    )


__all__ = (
    "DEFAULT_BACKGROUND_COLOR",
    "DEFAULT_PADDING_PIXELS",
    "DEFAULT_SAMPLES_PER_AXIS",
    "DEFAULT_TEXTURE_SIZE",
    "MAX_TEXTURE_DIMENSION",
    "RGBA",
    "SurfaceColorSample",
    "SurfaceColorSampler",
    "TextureBuffer",
    "UVBakeConfig",
    "UVBakeProgress",
    "UVBakeProgressCallback",
    "UVBakeResult",
    "UVBakeStats",
    "UVBakeTriangle",
    "UVBakeVertex",
    "Vector2",
    "Vector3",
    "bake_uv_texture",
    "square_texture_config",
    "texture_memory_bytes",
)