from __future__ import annotations

import math

from array import array
from dataclasses import (
    dataclass,
    replace,
)

import bpy

from .image_mask import BinaryMask
from .material_blend import (
    MaterialBlendConfig,
    MaterialColorCandidate,
    blend_candidates,
    choose_best_candidate,
)
from .material_visibility import (
    MeshVisibilityTester,
    VisibilityConfig,
)
from .projection_math import (
    ProjectionTransform,
    clamp01,
    compile_projection,
    direction_to_camera,
    dot3,
    normalize3,
    project_surface_position,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

COLOR_ATTRIBUTE_NAME = (
    "bpt_projected_color"
)

MATERIAL_NAME = (
    "BPT Projected Material"
)

MATERIAL_MODE = (
    "projected-color-v1.2"
)

VISIBILITY_MODE = (
    "raycast-v1"
)

BLEND_MODE = (
    "adaptive-topk-v1"
)

DEFAULT_FALLBACK_COLOR = (
    0.18,
    0.18,
    0.18,
    1.0,
)

MIN_ALPHA = 1e-4

MIN_BASE_WEIGHT = 1e-8


# ---------------------------------------------------------
# Backface fallback
#
# V1.1 deliberately allowed even weakly aligned views to
# fill surfaces not covered by a front-facing source.
#
# V1.2 keeps that safety net, but selection still goes
# through material_blend.py.
# ---------------------------------------------------------

FALLBACK_FACING_FLOOR = 0.05


# ---------------------------------------------------------
# Image data
# ---------------------------------------------------------

@dataclass(frozen=True)
class ImageBuffer:
    """
    Blender image copied into a Python float buffer.

    Reading bpy.types.Image.pixels repeatedly through RNA
    is expensive, so every projection image is copied once.
    """

    width: int
    height: int

    pixels: array

    @classmethod
    def from_blender_image(
        cls,
        image: bpy.types.Image,
    ) -> "ImageBuffer":
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
                    f'Image "{image.name}" '
                    "has invalid dimensions: "
                    f"{width}x{height}."
                )
            )

        pixels = array(
            "f",
            [0.0],
        ) * (
            width
            * height
            * 4
        )

        image.pixels.foreach_get(
            pixels
        )

        return cls(
            width=width,
            height=height,
            pixels=pixels,
        )

    def rgba(
        self,
        x: int,
        y: int,
    ) -> tuple[
        float,
        float,
        float,
        float,
    ]:
        x = max(
            0,
            min(
                self.width - 1,
                int(x),
            ),
        )

        y = max(
            0,
            min(
                self.height - 1,
                int(y),
            ),
        )

        index = (
            (
                y
                * self.width
                + x
            )
            * 4
        )

        return (
            float(
                self.pixels[
                    index
                ]
            ),
            float(
                self.pixels[
                    index + 1
                ]
            ),
            float(
                self.pixels[
                    index + 2
                ]
            ),
            float(
                self.pixels[
                    index + 3
                ]
            ),
        )

    def sample_bilinear(
        self,
        u: float,
        v: float,
    ) -> tuple[
        float,
        float,
        float,
        float,
    ]:
        """
        Bilinear sampling in normalized image space.

        Blender image.pixels uses the same bottom-left
        convention as projection_math.py:

            u = 0 -> left
            u = 1 -> right

            v = 0 -> bottom
            v = 1 -> top
        """

        u = clamp01(
            u
        )

        v = clamp01(
            v
        )

        fx = (
            u
            * float(
                self.width
                - 1
            )
        )

        fy = (
            v
            * float(
                self.height
                - 1
            )
        )

        x0 = int(
            math.floor(
                fx
            )
        )

        y0 = int(
            math.floor(
                fy
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
            fx
            - float(
                x0
            )
        )

        ty = (
            fy
            - float(
                y0
            )
        )

        c00 = self.rgba(
            x0,
            y0,
        )

        c10 = self.rgba(
            x1,
            y0,
        )

        c01 = self.rgba(
            x0,
            y1,
        )

        c11 = self.rgba(
            x1,
            y1,
        )

        result: list[
            float
        ] = []

        for channel in range(
            4
        ):
            bottom = (
                c00[channel]
                * (
                    1.0
                    - tx
                )
                + c10[channel]
                * tx
            )

            top = (
                c01[channel]
                * (
                    1.0
                    - tx
                )
                + c11[channel]
                * tx
            )

            value = (
                bottom
                * (
                    1.0
                    - ty
                )
                + top
                * ty
            )

            result.append(
                float(
                    value
                )
            )

        return (
            result[0],
            result[1],
            result[2],
            result[3],
        )


# ---------------------------------------------------------
# Projection view
# ---------------------------------------------------------

@dataclass(frozen=True)
class ProjectedMaterialView:
    """
    One RGB projection participating in material selection.

    Geometry reconstruction and appearance remain separate:

        NativeProjection
            -> geometry

        ProjectedMaterialView
            -> appearance
    """

    name: str

    image: ImageBuffer

    transform: ProjectionTransform

    mask: BinaryMask | None

    camera_direction: tuple[
        float,
        float,
        float,
    ]

    weight: float = 1.0

    @classmethod
    def from_blender_image(
        cls,
        *,
        name: str,
        image: bpy.types.Image,
        azimuth_degrees: float,
        elevation_degrees: float,
        flip_x: bool = False,
        weight: float = 1.0,
        mask: BinaryMask | None = None,
    ) -> "ProjectedMaterialView":
        image_buffer = (
            ImageBuffer
            .from_blender_image(
                image
            )
        )

        if mask is not None:
            if (
                mask.width
                != image_buffer.width
                or mask.height
                != image_buffer.height
            ):
                raise ValueError(
                    (
                        f'Projection "{name}" '
                        "image/mask dimensions differ: "
                        f"image="
                        f"{image_buffer.width}x"
                        f"{image_buffer.height}, "
                        f"mask="
                        f"{mask.width}x"
                        f"{mask.height}."
                    )
                )

        normalized_weight = max(
            0.0,
            float(
                weight
            ),
        )

        return cls(
            name=str(
                name
            ),
            image=image_buffer,
            transform=(
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
            ),
            mask=mask,
            camera_direction=(
                direction_to_camera(
                    azimuth_degrees=(
                        azimuth_degrees
                    ),
                    elevation_degrees=(
                        elevation_degrees
                    ),
                )
            ),
            weight=(
                normalized_weight
            ),
        )


# ---------------------------------------------------------
# Public result statistics
# ---------------------------------------------------------

@dataclass(frozen=True)
class MaterialProjectionStats:
    vertex_count: int

    loop_count: int

    view_count: int

    projected_vertices: int

    fallback_vertices: int

    # -----------------------------------------------------
    # Compatibility counters.
    #
    # accepted_samples now means samples which ACTUALLY
    # contributed to a final vertex color.
    #
    # rejected_samples is every vertex/view pair which did
    # not contribute.
    # -----------------------------------------------------

    rejected_samples: int

    accepted_samples: int

    # -----------------------------------------------------
    # V1.2 diagnostics
    # -----------------------------------------------------

    candidate_samples: int

    source_rejected_samples: int

    visible_samples: int

    occluded_samples: int

    front_facing_samples: int

    backface_samples: int

    grazing_rejected_samples: int

    relative_rejected_samples: int

    top_k_rejected_samples: int

    selected_samples: int

    projected_fallback_vertices: int

    neutral_fallback_vertices: int


# ---------------------------------------------------------
# Per-vertex diagnostics
# ---------------------------------------------------------

@dataclass(frozen=True)
class ProjectedColorResult:
    color: tuple[
        float,
        float,
        float,
        float,
    ]

    used_fallback: bool

    total_samples: int

    candidate_samples: int

    source_rejected_samples: int

    visible_samples: int

    occluded_samples: int

    front_facing_samples: int

    backface_samples: int

    grazing_rejected_samples: int

    relative_rejected_samples: int

    top_k_rejected_samples: int

    selected_samples: int

    @property
    def accepted_samples(
        self,
    ) -> int:
        return (
            self.selected_samples
        )

    @property
    def rejected_samples(
        self,
    ) -> int:
        return max(
            0,
            self.total_samples
            - self.selected_samples,
        )


# ---------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------

@dataclass(frozen=True)
class _CandidateCollection:
    candidates: tuple[
        MaterialColorCandidate,
        ...
    ]

    total_samples: int

    candidate_samples: int

    source_rejected_samples: int

    visible_samples: int

    occluded_samples: int


# ---------------------------------------------------------
# Mask sampling
# ---------------------------------------------------------

def _sample_mask(
    mask: BinaryMask,
    u: float,
    v: float,
) -> bool:
    """
    Nearest-neighbour mask sampling.

    Deliberately matches native/src/visual_hull.cpp:

        int(
            u * (width - 1)
            + 0.5
        )
    """

    if (
        u < 0.0
        or u > 1.0
        or v < 0.0
        or v > 1.0
    ):
        return False

    x = int(
        (
            u
            * float(
                mask.width
                - 1
            )
        )
        + 0.5
    )

    y = int(
        (
            v
            * float(
                mask.height
                - 1
            )
        )
        + 0.5
    )

    x = max(
        0,
        min(
            mask.width - 1,
            x,
        ),
    )

    y = max(
        0,
        min(
            mask.height - 1,
            y,
        ),
    )

    return mask.get(
        x,
        y,
    )


# ---------------------------------------------------------
# Source sample
# ---------------------------------------------------------

def _sample_source_view(
    position: tuple[
        float,
        float,
        float,
    ],
    normal: tuple[
        float,
        float,
        float,
    ],
    view: ProjectedMaterialView,
    *,
    width: int,
    depth: int,
    height: int,
    voxel_size: float,
    center_xy: bool,
) -> MaterialColorCandidate | None:
    """
    Collect one geometrically plausible source sample.

    IMPORTANT:

    This function intentionally does NOT perform:

        - grazing rejection
        - relative score filtering
        - top-K filtering
        - weight sharpening

    Those decisions belong exclusively to
    material_blend.py.

    Visibility is also handled one level above so it can be
    counted independently.
    """

    projected = (
        project_surface_position(
            position,
            transform=(
                view.transform
            ),
            width=width,
            depth=depth,
            height=height,
            voxel_size=(
                voxel_size
            ),
            center_xy=(
                center_xy
            ),
        )
    )

    if not projected.inside:
        return None

    if (
        view.mask is not None
        and not _sample_mask(
            view.mask,
            projected.u,
            projected.v,
        )
    ):
        return None

    (
        red,
        green,
        blue,
        alpha,
    ) = (
        view.image
        .sample_bilinear(
            projected.u,
            projected.v,
        )
    )

    if (
        not math.isfinite(
            alpha
        )
        or alpha <= MIN_ALPHA
    ):
        return None

    base_weight = (
        view.weight
        * alpha
    )

    if (
        not math.isfinite(
            base_weight
        )
        or base_weight
        <= MIN_BASE_WEIGHT
    ):
        return None

    facing = dot3(
        normal,
        view.camera_direction,
    )

    if not math.isfinite(
        facing
    ):
        return None

    return MaterialColorCandidate(
        red=float(
            red
        ),
        green=float(
            green
        ),
        blue=float(
            blue
        ),
        alpha=float(
            alpha
        ),
        base_weight=float(
            base_weight
        ),
        facing=float(
            facing
        ),
        source_name=(
            view.name
        ),
    )


# ---------------------------------------------------------
# Visibility-filtered candidate collection
# ---------------------------------------------------------

def _collect_candidates(
    position: tuple[
        float,
        float,
        float,
    ],
    normal: tuple[
        float,
        float,
        float,
    ],
    views: list[
        ProjectedMaterialView
    ],
    *,
    width: int,
    depth: int,
    height: int,
    voxel_size: float,
    center_xy: bool,
    visibility_tester: (
        MeshVisibilityTester
        | None
    ),
) -> _CandidateCollection:
    """
    Build all RGB candidates once.

    Visibility is evaluated BEFORE material blending.

    This means material_blend.py never needs Blender,
    BVHTree, projection transforms or source images.

    For V1.2 we deliberately visibility-test every valid
    projected candidate, including back-facing candidates.

    Benefits:

        - visible_samples and occluded_samples are exact;
        - candidate_samples =
              visible_samples + occluded_samples
          whenever visibility is enabled;
        - fallback does not need to raycast a second time.
    """

    total_samples = len(
        views
    )

    candidate_samples = 0

    source_rejected_samples = 0

    visible_samples = 0

    occluded_samples = 0

    candidates: list[
        MaterialColorCandidate
    ] = []

    for view in views:
        candidate = (
            _sample_source_view(
                position,
                normal,
                view,
                width=width,
                depth=depth,
                height=height,
                voxel_size=(
                    voxel_size
                ),
                center_xy=(
                    center_xy
                ),
            )
        )

        if candidate is None:
            source_rejected_samples += 1
            continue

        candidate_samples += 1

        if visibility_tester is not None:
            visibility = (
                visibility_tester
                .query(
                    position,
                    view.camera_direction,
                )
            )

            if not visibility.visible:
                occluded_samples += 1
                continue

        visible_samples += 1

        candidates.append(
            candidate
        )

    return _CandidateCollection(
        candidates=tuple(
            candidates
        ),
        total_samples=(
            total_samples
        ),
        candidate_samples=(
            candidate_samples
        ),
        source_rejected_samples=(
            source_rejected_samples
        ),
        visible_samples=(
            visible_samples
        ),
        occluded_samples=(
            occluded_samples
        ),
    )


# ---------------------------------------------------------
# Config
# ---------------------------------------------------------

def _resolve_blend_config(
    blend_config: (
        MaterialBlendConfig
        | None
    ),
    *,
    facing_power: float,
) -> MaterialBlendConfig:
    """
    Preserve the historical facing_power argument.

    If an explicit V1.2 MaterialBlendConfig is supplied,
    that config owns facing_power as well.
    """

    if blend_config is None:
        resolved = MaterialBlendConfig(
            facing_power=float(
                facing_power
            )
        )

    else:
        resolved = (
            blend_config
        )

    resolved.validate()

    return resolved


# ---------------------------------------------------------
# Color helpers
# ---------------------------------------------------------

def _opaque_color(
    color: tuple[
        float,
        float,
        float,
        float,
    ],
) -> tuple[
    float,
    float,
    float,
    float,
]:
    """
    Projected material remains opaque.

    Source alpha is a confidence/input mask signal, not an
    output transparency channel.
    """

    return (
        clamp01(
            color[0]
        ),
        clamp01(
            color[1]
        ),
        clamp01(
            color[2]
        ),
        1.0,
    )


def _fallback_candidates(
    candidates: tuple[
        MaterialColorCandidate,
        ...
    ],
) -> list[
    MaterialColorCandidate
]:
    """
    Prepare candidates for the V1-compatible safety fallback.

    Absolute alignment is used and a small floor prevents
    perfectly perpendicular candidates from becoming
    impossible to select.

    This approximates V1.1's historical:

        max(
            0.05,
            abs(facing) ** power
        )

    while keeping actual ranking inside material_blend.py.
    """

    result: list[
        MaterialColorCandidate
    ] = []

    for candidate in candidates:
        result.append(
            replace(
                candidate,
                facing=max(
                    FALLBACK_FACING_FLOOR,
                    abs(
                        candidate.facing
                    ),
                ),
            )
        )

    return result


# ---------------------------------------------------------
# Detailed multi-view blend
# ---------------------------------------------------------

def _blend_projected_color_detailed(
    position: tuple[
        float,
        float,
        float,
    ],
    normal: tuple[
        float,
        float,
        float,
    ],
    views: list[
        ProjectedMaterialView
    ],
    *,
    width: int,
    depth: int,
    height: int,
    voxel_size: float = 1.0,
    center_xy: bool = True,
    facing_power: float = 2.0,
    fallback_color: tuple[
        float,
        float,
        float,
        float,
    ] = DEFAULT_FALLBACK_COLOR,
    allow_backface_fallback: bool = True,
    visibility_tester: (
        MeshVisibilityTester
        | None
    ) = None,
    blend_config: (
        MaterialBlendConfig
        | None
    ) = None,
) -> ProjectedColorResult:
    """
    V1.2 material projection for one surface point.

    Pipeline:

        source projection
              ↓
        mask / alpha / weight
              ↓
        visibility V1.1
              ↓
        front-facing candidates
              ↓
        MaterialBlendConfig
              ↓
        grazing cutoff
              ↓
        relative score cutoff
              ↓
        top-K
              ↓
        weight sharpening
              ↓
        normalized blend

    If the main pass cannot select anything, an optional
    single-view fallback is attempted using absolute facing.

    Diagnostic pruning counters always describe the main
    adaptive V1.2 pass. The fallback is a recovery path and
    must not overwrite the reason the primary pass failed.
    """

    resolved_config = (
        _resolve_blend_config(
            blend_config,
            facing_power=(
                facing_power
            ),
        )
    )

    if not views:
        return ProjectedColorResult(
            color=(
                fallback_color
            ),
            used_fallback=True,
            total_samples=0,
            candidate_samples=0,
            source_rejected_samples=0,
            visible_samples=0,
            occluded_samples=0,
            front_facing_samples=0,
            backface_samples=0,
            grazing_rejected_samples=0,
            relative_rejected_samples=0,
            top_k_rejected_samples=0,
            selected_samples=0,
        )

    normalized_normal = normalize3(
        normal
    )

    collection = (
        _collect_candidates(
            position,
            normalized_normal,
            views,
            width=width,
            depth=depth,
            height=height,
            voxel_size=(
                voxel_size
            ),
            center_xy=(
                center_xy
            ),
            visibility_tester=(
                visibility_tester
            ),
        )
    )

    front_candidates = [
        candidate
        for candidate
        in collection.candidates
        if candidate.facing > 0.0
    ]

    front_facing_samples = len(
        front_candidates
    )

    backface_samples = (
        collection.visible_samples
        - front_facing_samples
    )

    # -----------------------------------------------------
    # Main V1.2 blend
    # -----------------------------------------------------

    main_result = (
        blend_candidates(
            front_candidates,
            resolved_config,
            use_absolute_facing=False,
        )
    )

    if (
        main_result.has_selection
        and main_result.color
        is not None
    ):
        return ProjectedColorResult(
            color=(
                _opaque_color(
                    main_result.color
                )
            ),
            used_fallback=False,
            total_samples=(
                collection.total_samples
            ),
            candidate_samples=(
                collection
                .candidate_samples
            ),
            source_rejected_samples=(
                collection
                .source_rejected_samples
            ),
            visible_samples=(
                collection
                .visible_samples
            ),
            occluded_samples=(
                collection
                .occluded_samples
            ),
            front_facing_samples=(
                front_facing_samples
            ),
            backface_samples=(
                backface_samples
            ),
            grazing_rejected_samples=(
                main_result
                .grazing_rejected_count
            ),
            relative_rejected_samples=(
                main_result
                .relative_rejected_count
            ),
            top_k_rejected_samples=(
                main_result
                .top_k_rejected_count
            ),
            selected_samples=(
                main_result
                .selected_count
            ),
        )

    # -----------------------------------------------------
    # Safety fallback.
    #
    # The purpose is not to blur every unknown surface with
    # every camera.
    #
    # Exactly one visible source is selected.
    #
    # IMPORTANT:
    #
    # The fallback is only a recovery strategy. Diagnostic
    # pruning counters below keep the main_result values,
    # because they explain why the normal V1.2 blend could
    # not produce a color.
    # -----------------------------------------------------

    if (
        allow_backface_fallback
        and collection.candidates
    ):
        fallback_config = replace(
            resolved_config,
            min_facing=0.0,
            relative_score_cutoff=0.0,
        )

        fallback_result = (
            choose_best_candidate(
                _fallback_candidates(
                    collection.candidates
                ),
                fallback_config,
                use_absolute_facing=False,
            )
        )

        if (
            fallback_result.has_selection
            and fallback_result.color
            is not None
        ):
            return ProjectedColorResult(
                color=(
                    _opaque_color(
                        fallback_result.color
                    )
                ),
                used_fallback=True,
                total_samples=(
                    collection.total_samples
                ),
                candidate_samples=(
                    collection
                    .candidate_samples
                ),
                source_rejected_samples=(
                    collection
                    .source_rejected_samples
                ),
                visible_samples=(
                    collection
                    .visible_samples
                ),
                occluded_samples=(
                    collection
                    .occluded_samples
                ),
                front_facing_samples=(
                    front_facing_samples
                ),
                backface_samples=(
                    backface_samples
                ),

                # -----------------------------------------
                # These counters deliberately describe the
                # PRIMARY V1.2 pass.
                #
                # The previous implementation accidentally
                # replaced them with fallback_result values,
                # hiding cases such as:
                #
                #   facing 0.05
                #   min_facing 0.10
                #       ↓
                #   main grazing rejection
                #       ↓
                #   fallback succeeds
                #
                # That must still report one grazing reject.
                # -----------------------------------------

                grazing_rejected_samples=(
                    main_result
                    .grazing_rejected_count
                ),
                relative_rejected_samples=(
                    main_result
                    .relative_rejected_count
                ),
                top_k_rejected_samples=(
                    main_result
                    .top_k_rejected_count
                ),

                # The final color does come from fallback,
                # so selected_samples belongs to the actual
                # fallback result.
                selected_samples=(
                    fallback_result
                    .selected_count
                ),
            )

    # -----------------------------------------------------
    # Neutral fallback
    # -----------------------------------------------------

    return ProjectedColorResult(
        color=(
            fallback_color
        ),
        used_fallback=True,
        total_samples=(
            collection.total_samples
        ),
        candidate_samples=(
            collection
            .candidate_samples
        ),
        source_rejected_samples=(
            collection
            .source_rejected_samples
        ),
        visible_samples=(
            collection
            .visible_samples
        ),
        occluded_samples=(
            collection
            .occluded_samples
        ),
        front_facing_samples=(
            front_facing_samples
        ),
        backface_samples=(
            backface_samples
        ),
        grazing_rejected_samples=(
            main_result
            .grazing_rejected_count
        ),
        relative_rejected_samples=(
            main_result
            .relative_rejected_count
        ),
        top_k_rejected_samples=(
            main_result
            .top_k_rejected_count
        ),
        selected_samples=0,
    )


# ---------------------------------------------------------
# Compatibility public blend API
# ---------------------------------------------------------

def blend_projected_color(
    position: tuple[
        float,
        float,
        float,
    ],
    normal: tuple[
        float,
        float,
        float,
    ],
    views: list[
        ProjectedMaterialView
    ],
    *,
    width: int,
    depth: int,
    height: int,
    voxel_size: float = 1.0,
    center_xy: bool = True,
    facing_power: float = 2.0,
    fallback_color: tuple[
        float,
        float,
        float,
        float,
    ] = DEFAULT_FALLBACK_COLOR,
    allow_backface_fallback: bool = True,
    visibility_tester: (
        MeshVisibilityTester
        | None
    ) = None,
    blend_config: (
        MaterialBlendConfig
        | None
    ) = None,
) -> tuple[
    tuple[
        float,
        float,
        float,
        float,
    ],
    int,
    int,
    bool,
]:
    """
    Compatibility wrapper.

    Existing callers still receive:

        (
            RGBA,
            accepted_sample_count,
            rejected_sample_count,
            used_fallback,
        )

    V1.2 semantics:

        accepted_sample_count
            = number of samples actually contributing to
              the final color;

        rejected_sample_count
            = every view which did not contribute.
    """

    result = (
        _blend_projected_color_detailed(
            position,
            normal,
            views,
            width=width,
            depth=depth,
            height=height,
            voxel_size=(
                voxel_size
            ),
            center_xy=(
                center_xy
            ),
            facing_power=(
                facing_power
            ),
            fallback_color=(
                fallback_color
            ),
            allow_backface_fallback=(
                allow_backface_fallback
            ),
            visibility_tester=(
                visibility_tester
            ),
            blend_config=(
                blend_config
            ),
        )
    )

    return (
        result.color,
        result.accepted_samples,
        result.rejected_samples,
        result.used_fallback,
    )


# ---------------------------------------------------------
# Blender color attribute
# ---------------------------------------------------------

def _ensure_color_attribute(
    mesh: bpy.types.Mesh,
    *,
    attribute_name: str,
):
    existing = (
        mesh.color_attributes.get(
            attribute_name
        )
    )

    if existing is not None:
        if (
            existing.domain
            != "CORNER"
            or existing.data_type
            != "FLOAT_COLOR"
        ):
            mesh.color_attributes.remove(
                existing
            )

            existing = None

    if existing is None:
        existing = (
            mesh.color_attributes.new(
                name=attribute_name,
                type="FLOAT_COLOR",
                domain="CORNER",
            )
        )

    return existing


# ---------------------------------------------------------
# Blender material
# ---------------------------------------------------------

def ensure_projected_material(
    *,
    attribute_name: str = (
        COLOR_ATTRIBUTE_NAME
    ),
    material_name: str = (
        MATERIAL_NAME
    ),
) -> bpy.types.Material:
    material = (
        bpy.data.materials.get(
            material_name
        )
    )

    if material is None:
        material = (
            bpy.data.materials.new(
                name=material_name
            )
        )

    material.use_nodes = True

    node_tree = (
        material.node_tree
    )

    if node_tree is None:
        raise RuntimeError(
            (
                "Could not create material "
                "node tree."
            )
        )

    nodes = (
        node_tree.nodes
    )

    links = (
        node_tree.links
    )

    nodes.clear()

    output = nodes.new(
        "ShaderNodeOutputMaterial"
    )

    output.name = (
        "BPT Material Output"
    )

    output.label = (
        "BPT Material Output"
    )

    output.location = (
        420.0,
        0.0,
    )

    principled = nodes.new(
        "ShaderNodeBsdfPrincipled"
    )

    principled.name = (
        "BPT Principled"
    )

    principled.label = (
        "Projected Material"
    )

    principled.location = (
        120.0,
        0.0,
    )

    # -----------------------------------------------------
    # Neutral material defaults
    # -----------------------------------------------------

    if (
        "Metallic"
        in principled.inputs
    ):
        principled.inputs[
            "Metallic"
        ].default_value = 0.0

    if (
        "Roughness"
        in principled.inputs
    ):
        principled.inputs[
            "Roughness"
        ].default_value = 0.65

    # -----------------------------------------------------
    # Color attribute
    # -----------------------------------------------------

    try:
        color_node = nodes.new(
            "ShaderNodeVertexColor"
        )

        color_node.layer_name = (
            attribute_name
        )

    except RuntimeError:
        color_node = nodes.new(
            "ShaderNodeAttribute"
        )

        color_node.attribute_name = (
            attribute_name
        )

    color_node.name = (
        "BPT Projected Color"
    )

    color_node.label = (
        attribute_name
    )

    color_node.location = (
        -220.0,
        20.0,
    )

    color_output = (
        color_node.outputs.get(
            "Color"
        )
    )

    base_color_input = (
        principled.inputs.get(
            "Base Color"
        )
    )

    if (
        color_output is None
        or base_color_input is None
    ):
        raise RuntimeError(
            (
                "Could not connect projected "
                "color to Principled BSDF."
            )
        )

    links.new(
        color_output,
        base_color_input,
    )

    links.new(
        principled.outputs[
            "BSDF"
        ],
        output.inputs[
            "Surface"
        ],
    )

    return material


# ---------------------------------------------------------
# Apply projected material
# ---------------------------------------------------------

def apply_projected_material(
    obj: bpy.types.Object,
    views: list[
        ProjectedMaterialView
    ],
    *,
    volume_width: int,
    volume_depth: int,
    volume_height: int,
    voxel_size: float = 1.0,
    center_xy: bool = True,
    attribute_name: str = (
        COLOR_ATTRIBUTE_NAME
    ),
    material_name: str = (
        MATERIAL_NAME
    ),
    facing_power: float = 2.0,
    fallback_color: tuple[
        float,
        float,
        float,
        float,
    ] = DEFAULT_FALLBACK_COLOR,
    allow_backface_fallback: bool = True,
    replace_materials: bool = True,
    enable_visibility: bool = True,
    visibility_config: (
        VisibilityConfig
        | None
    ) = None,
    visibility_tester: (
        MeshVisibilityTester
        | None
    ) = None,
    blend_config: (
        MaterialBlendConfig
        | None
    ) = None,
) -> MaterialProjectionStats:
    """
    Project source images onto one generated mesh.

    IMPORTANT:

    Call this while obj.data remains in native reconstruction
    coordinates.

    Do this BEFORE scale_object_to_height() or arbitrary mesh
    transforms.

    ---------------------------------------------------------
    V1.1
    ---------------------------------------------------------

        visibility / occlusion via one mesh-local BVH

    ---------------------------------------------------------
    V1.2
    ---------------------------------------------------------

        smooth grazing cutoff
            +
        relative candidate cutoff
            +
        top-K contributor selection
            +
        weight sharpening

    `blend_config` owns V1.2 selection parameters.

    If omitted, defaults are:

        min_facing             = 0.10
        facing_power           = facing_power argument
        relative_score_cutoff  = 0.20
        max_contributors       = 3
        weight_power           = 1.5
    """

    if obj.type != "MESH":
        raise TypeError(
            (
                "Projected material target "
                "must be a mesh object."
            )
        )

    if not views:
        raise ValueError(
            (
                "At least one material "
                "projection is required."
            )
        )

    if (
        volume_width <= 0
        or volume_depth <= 0
        or volume_height <= 0
    ):
        raise ValueError(
            (
                "Volume dimensions must be "
                "greater than zero."
            )
        )

    if (
        not math.isfinite(
            voxel_size
        )
        or voxel_size <= 0.0
    ):
        raise ValueError(
            (
                "voxel_size must be finite "
                "and greater than zero."
            )
        )

    if (
        not enable_visibility
        and visibility_tester
        is not None
    ):
        raise ValueError(
            (
                "visibility_tester cannot "
                "be provided when "
                "enable_visibility is False."
            )
        )

    if (
        visibility_tester is not None
        and visibility_config is not None
    ):
        raise ValueError(
            (
                "visibility_config cannot "
                "be combined with an explicit "
                "visibility_tester."
            )
        )

    resolved_blend_config = (
        _resolve_blend_config(
            blend_config,
            facing_power=(
                facing_power
            ),
        )
    )

    mesh = obj.data

    mesh.update()

    vertex_count = len(
        mesh.vertices
    )

    loop_count = len(
        mesh.loops
    )

    if vertex_count == 0:
        raise ValueError(
            (
                "Cannot project material "
                "onto an empty mesh."
            )
        )

    if loop_count == 0:
        raise ValueError(
            (
                "Cannot project material "
                "onto a mesh without loops."
            )
        )

    # -----------------------------------------------------
    # Visibility BVH
    #
    # Built ONCE per mesh.
    # -----------------------------------------------------

    active_visibility_tester: (
        MeshVisibilityTester
        | None
    )

    if enable_visibility:
        active_visibility_tester = (
            visibility_tester
        )

        if (
            active_visibility_tester
            is None
        ):
            active_visibility_tester = (
                MeshVisibilityTester
                .from_blender_object(
                    obj,
                    config=(
                        visibility_config
                    ),
                )
            )

    else:
        active_visibility_tester = (
            None
        )

    # -----------------------------------------------------
    # One color per mesh vertex
    # -----------------------------------------------------

    vertex_colors: list[
        tuple[
            float,
            float,
            float,
            float,
        ]
    ] = [
        fallback_color
    ] * vertex_count

    projected_vertices = 0

    fallback_vertices = 0

    projected_fallback_vertices = 0

    neutral_fallback_vertices = 0

    # -----------------------------------------------------
    # Aggregated sample metrics
    # -----------------------------------------------------

    accepted_samples = 0

    rejected_samples = 0

    candidate_samples = 0

    source_rejected_samples = 0

    visible_samples = 0

    occluded_samples = 0

    front_facing_samples = 0

    backface_samples = 0

    grazing_rejected_samples = 0

    relative_rejected_samples = 0

    top_k_rejected_samples = 0

    selected_samples = 0

    # -----------------------------------------------------
    # Projection
    # -----------------------------------------------------

    for vertex in mesh.vertices:
        position = (
            float(
                vertex.co.x
            ),
            float(
                vertex.co.y
            ),
            float(
                vertex.co.z
            ),
        )

        normal = normalize3(
            (
                float(
                    vertex.normal.x
                ),
                float(
                    vertex.normal.y
                ),
                float(
                    vertex.normal.z
                ),
            )
        )

        result = (
            _blend_projected_color_detailed(
                position,
                normal,
                views,
                width=volume_width,
                depth=volume_depth,
                height=volume_height,
                voxel_size=(
                    voxel_size
                ),
                center_xy=(
                    center_xy
                ),
                facing_power=(
                    facing_power
                ),
                fallback_color=(
                    fallback_color
                ),
                allow_backface_fallback=(
                    allow_backface_fallback
                ),
                visibility_tester=(
                    active_visibility_tester
                ),
                blend_config=(
                    resolved_blend_config
                ),
            )
        )

        vertex_colors[
            vertex.index
        ] = result.color

        accepted_samples += (
            result.accepted_samples
        )

        rejected_samples += (
            result.rejected_samples
        )

        candidate_samples += (
            result.candidate_samples
        )

        source_rejected_samples += (
            result
            .source_rejected_samples
        )

        visible_samples += (
            result.visible_samples
        )

        occluded_samples += (
            result.occluded_samples
        )

        front_facing_samples += (
            result.front_facing_samples
        )

        backface_samples += (
            result.backface_samples
        )

        grazing_rejected_samples += (
            result
            .grazing_rejected_samples
        )

        relative_rejected_samples += (
            result
            .relative_rejected_samples
        )

        top_k_rejected_samples += (
            result
            .top_k_rejected_samples
        )

        selected_samples += (
            result.selected_samples
        )

        if result.used_fallback:
            fallback_vertices += 1

            if (
                result.selected_samples
                > 0
            ):
                projected_fallback_vertices += 1

            else:
                neutral_fallback_vertices += 1

        else:
            projected_vertices += 1

    # -----------------------------------------------------
    # Vertex colors -> CORNER colors
    # -----------------------------------------------------

    color_attribute = (
        _ensure_color_attribute(
            mesh,
            attribute_name=(
                attribute_name
            ),
        )
    )

    corner_colors = array(
        "f"
    )

    for loop in mesh.loops:
        color = vertex_colors[
            loop.vertex_index
        ]

        corner_colors.extend(
            color
        )

    expected_float_count = (
        loop_count
        * 4
    )

    if (
        len(
            corner_colors
        )
        != expected_float_count
    ):
        raise RuntimeError(
            (
                "Projected color buffer "
                "size mismatch."
            )
        )

    color_attribute.data.foreach_set(
        "color",
        corner_colors,
    )

    # -----------------------------------------------------
    # Blender material
    # -----------------------------------------------------

    material = (
        ensure_projected_material(
            attribute_name=(
                attribute_name
            ),
            material_name=(
                material_name
            ),
        )
    )

    if replace_materials:
        mesh.materials.clear()

    material_names = {
        item.name
        for item
        in mesh.materials
        if item is not None
    }

    if (
        material.name
        not in material_names
    ):
        mesh.materials.append(
            material
        )

    for polygon in mesh.polygons:
        polygon.material_index = 0

    mesh.update()

    # -----------------------------------------------------
    # Metadata — public identity
    # -----------------------------------------------------

    obj[
        "bpt_material"
    ] = (
        MATERIAL_MODE
    )

    obj[
        "bpt_material_views"
    ] = len(
        views
    )

    obj[
        "bpt_material_attribute"
    ] = (
        attribute_name
    )

    obj[
        "bpt_material_projected_vertices"
    ] = (
        projected_vertices
    )

    obj[
        "bpt_material_fallback_vertices"
    ] = (
        fallback_vertices
    )

    obj[
        "bpt_material_projected_fallback_vertices"
    ] = (
        projected_fallback_vertices
    )

    obj[
        "bpt_material_neutral_fallback_vertices"
    ] = (
        neutral_fallback_vertices
    )

    # -----------------------------------------------------
    # Metadata — visibility
    # -----------------------------------------------------

    obj[
        "bpt_material_visibility"
    ] = (
        active_visibility_tester
        is not None
    )

    obj[
        "bpt_material_visibility_mode"
    ] = (
        VISIBILITY_MODE
        if active_visibility_tester
        is not None
        else "disabled"
    )

    if (
        active_visibility_tester
        is not None
    ):
        obj[
            "bpt_material_visibility_epsilon"
        ] = (
            active_visibility_tester
            .surface_epsilon
        )

        obj[
            "bpt_material_visibility_max_distance"
        ] = (
            active_visibility_tester
            .max_distance
        )

    # -----------------------------------------------------
    # Metadata — V1.2 blend configuration
    # -----------------------------------------------------

    obj[
        "bpt_material_blend_mode"
    ] = (
        BLEND_MODE
    )

    obj[
        "bpt_material_blend_min_facing"
    ] = (
        resolved_blend_config
        .min_facing
    )

    obj[
        "bpt_material_blend_facing_power"
    ] = (
        resolved_blend_config
        .facing_power
    )

    obj[
        "bpt_material_blend_relative_score_cutoff"
    ] = (
        resolved_blend_config
        .relative_score_cutoff
    )

    obj[
        "bpt_material_blend_max_contributors"
    ] = (
        resolved_blend_config
        .max_contributors
    )

    obj[
        "bpt_material_blend_weight_power"
    ] = (
        resolved_blend_config
        .weight_power
    )

    # -----------------------------------------------------
    # Metadata — diagnostics
    # -----------------------------------------------------

    obj[
        "bpt_material_accepted_samples"
    ] = (
        accepted_samples
    )

    obj[
        "bpt_material_rejected_samples"
    ] = (
        rejected_samples
    )

    obj[
        "bpt_material_candidate_samples"
    ] = (
        candidate_samples
    )

    obj[
        "bpt_material_source_rejected_samples"
    ] = (
        source_rejected_samples
    )

    obj[
        "bpt_material_visible_samples"
    ] = (
        visible_samples
    )

    obj[
        "bpt_material_occluded_samples"
    ] = (
        occluded_samples
    )

    obj[
        "bpt_material_front_facing_samples"
    ] = (
        front_facing_samples
    )

    obj[
        "bpt_material_backface_samples"
    ] = (
        backface_samples
    )

    obj[
        "bpt_material_grazing_rejected_samples"
    ] = (
        grazing_rejected_samples
    )

    obj[
        "bpt_material_relative_rejected_samples"
    ] = (
        relative_rejected_samples
    )

    obj[
        "bpt_material_top_k_rejected_samples"
    ] = (
        top_k_rejected_samples
    )

    obj[
        "bpt_material_selected_samples"
    ] = (
        selected_samples
    )

    # -----------------------------------------------------
    # Result
    # -----------------------------------------------------

    return MaterialProjectionStats(
        vertex_count=(
            vertex_count
        ),
        loop_count=(
            loop_count
        ),
        view_count=len(
            views
        ),
        projected_vertices=(
            projected_vertices
        ),
        fallback_vertices=(
            fallback_vertices
        ),
        rejected_samples=(
            rejected_samples
        ),
        accepted_samples=(
            accepted_samples
        ),
        candidate_samples=(
            candidate_samples
        ),
        source_rejected_samples=(
            source_rejected_samples
        ),
        visible_samples=(
            visible_samples
        ),
        occluded_samples=(
            occluded_samples
        ),
        front_facing_samples=(
            front_facing_samples
        ),
        backface_samples=(
            backface_samples
        ),
        grazing_rejected_samples=(
            grazing_rejected_samples
        ),
        relative_rejected_samples=(
            relative_rejected_samples
        ),
        top_k_rejected_samples=(
            top_k_rejected_samples
        ),
        selected_samples=(
            selected_samples
        ),
        projected_fallback_vertices=(
            projected_fallback_vertices
        ),
        neutral_fallback_vertices=(
            neutral_fallback_vertices
        ),
    )