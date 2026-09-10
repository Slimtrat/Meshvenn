from __future__ import annotations

import math

from array import array
from dataclasses import dataclass

import bpy

from .image_mask import BinaryMask
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
    "projected-color-v1.1"
)

VISIBILITY_MODE = (
    "raycast-v1"
)

LEGACY_MATERIAL_MODE = (
    "projected-color-v1"
)

DEFAULT_FALLBACK_COLOR = (
    0.18,
    0.18,
    0.18,
    1.0,
)

MIN_ALPHA = 1e-4
MIN_WEIGHT = 1e-8


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

        Blender image.pixels follows the same bottom-left
        UV convention used by projection_math.py:

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
    One RGB projection participating in material blending.

    This is intentionally separate from NativeProjection.

    NativeProjection belongs to geometry reconstruction.
    ProjectedMaterialView belongs to appearance.
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
            weight=max(
                0.0,
                float(
                    weight
                ),
            ),
        )


# ---------------------------------------------------------
# Result statistics
# ---------------------------------------------------------

@dataclass(frozen=True)
class MaterialProjectionStats:
    vertex_count: int

    loop_count: int

    view_count: int

    projected_vertices: int

    fallback_vertices: int

    rejected_samples: int

    accepted_samples: int


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

    The rounding deliberately matches
    native/src/visual_hull.cpp:

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
# View weighting
# ---------------------------------------------------------

def _facing_weight(
    normal: tuple[
        float,
        float,
        float,
    ],
    view: ProjectedMaterialView,
    *,
    facing_power: float,
) -> float:
    facing = dot3(
        normal,
        view.camera_direction,
    )

    if facing <= 0.0:
        return 0.0

    facing = clamp01(
        facing
    )

    if facing_power <= 0.0:
        return 1.0

    return (
        facing
        ** facing_power
    )


# ---------------------------------------------------------
# Single-view sample
# ---------------------------------------------------------

@dataclass(frozen=True)
class _CandidateSample:
    red: float
    green: float
    blue: float
    alpha: float

    weight: float

    facing: float


def _sample_view(
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
    facing_power: float,
    require_front_facing: bool,
    visibility_tester: (
        MeshVisibilityTester
        | None
    ) = None,
) -> _CandidateSample | None:
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

    if alpha <= MIN_ALPHA:
        return None

    raw_facing = dot3(
        normal,
        view.camera_direction,
    )

    facing = max(
        0.0,
        raw_facing,
    )

    if require_front_facing:
        if facing <= 0.0:
            return None

        facing_factor = (
            _facing_weight(
                normal,
                view,
                facing_power=(
                    facing_power
                ),
            )
        )

    else:
        # -------------------------------------------------
        # Fallback.
        #
        # If no front-facing image can color the point,
        # still prefer the view whose axis is most aligned
        # with the surface.
        #
        # V1.1 keeps this fallback, but an explicitly
        # occluded view is no longer allowed to color the
        # point.
        # -------------------------------------------------

        facing_factor = max(
            0.05,
            abs(
                raw_facing
            )
            ** max(
                facing_power,
                1.0,
            ),
        )

    sample_weight = (
        view.weight
        * alpha
        * facing_factor
    )

    if (
        sample_weight
        <= MIN_WEIGHT
    ):
        return None

    # -----------------------------------------------------
    # V1.1 visibility rejection.
    #
    # Only pay the BVH raycast cost after the projection
    # has survived:
    #
    # - UV bounds
    # - silhouette
    # - image alpha
    # - normal orientation
    # - effective sample weight
    #
    # camera_direction points from the object toward the
    # source camera, which is exactly the direction expected
    # by MeshVisibilityTester.
    # -----------------------------------------------------

    if (
        visibility_tester is not None
        and not visibility_tester
        .is_visible(
            position,
            view.camera_direction,
        )
    ):
        return None

    return _CandidateSample(
        red=red,
        green=green,
        blue=blue,
        alpha=alpha,
        weight=sample_weight,
        facing=raw_facing,
    )


# ---------------------------------------------------------
# Multi-view blend
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
    Blend all valid source projections for one surface point.

    Return:

        (
            RGBA,
            accepted_sample_count,
            rejected_sample_count,
            used_fallback,
        )

    rejected_sample_count includes every rejection reason:

        - projection bounds
        - silhouette mask
        - image alpha
        - orientation
        - negligible weight
        - V1.1 visibility / occlusion

    The blending weights themselves are unchanged from V1.

    V1.1 only removes candidates which are not directly
    visible from their source camera.
    """

    if not views:
        return (
            fallback_color,
            0,
            0,
            True,
        )

    normal = normalize3(
        normal
    )

    weighted_red = 0.0
    weighted_green = 0.0
    weighted_blue = 0.0

    total_weight = 0.0

    accepted = 0
    rejected = 0

    # -----------------------------------------------------
    # Main pass:
    # only front-facing projections participate.
    # -----------------------------------------------------

    for view in views:
        candidate = (
            _sample_view(
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
                facing_power=(
                    facing_power
                ),
                require_front_facing=True,
                visibility_tester=(
                    visibility_tester
                ),
            )
        )

        if candidate is None:
            rejected += 1
            continue

        accepted += 1

        weighted_red += (
            candidate.red
            * candidate.weight
        )

        weighted_green += (
            candidate.green
            * candidate.weight
        )

        weighted_blue += (
            candidate.blue
            * candidate.weight
        )

        total_weight += (
            candidate.weight
        )

    if total_weight > MIN_WEIGHT:
        inverse = (
            1.0
            / total_weight
        )

        return (
            (
                clamp01(
                    weighted_red
                    * inverse
                ),
                clamp01(
                    weighted_green
                    * inverse
                ),
                clamp01(
                    weighted_blue
                    * inverse
                ),
                1.0,
            ),
            accepted,
            rejected,
            False,
        )

    # -----------------------------------------------------
    # Fallback pass.
    #
    # A reconstruction can legitimately contain surfaces
    # for which no input camera is front-facing.
    #
    # We keep V1's fallback selection semantics.
    #
    # V1.1 also applies visibility to fallback views:
    # an occluded source can never paint through another
    # part of the reconstructed mesh.
    # -----------------------------------------------------

    if allow_backface_fallback:
        best_candidate: (
            _CandidateSample
            | None
        ) = None

        for view in views:
            candidate = (
                _sample_view(
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
                    facing_power=(
                        facing_power
                    ),
                    require_front_facing=False,
                    visibility_tester=(
                        visibility_tester
                    ),
                )
            )

            if candidate is None:
                continue

            if (
                best_candidate is None
                or candidate.weight
                > best_candidate.weight
            ):
                best_candidate = (
                    candidate
                )

        if best_candidate is not None:
            return (
                (
                    clamp01(
                        best_candidate.red
                    ),
                    clamp01(
                        best_candidate.green
                    ),
                    clamp01(
                        best_candidate.blue
                    ),
                    1.0,
                ),
                accepted + 1,
                rejected,
                True,
            )

    return (
        fallback_color,
        accepted,
        rejected,
        True,
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
    # Neutral physical defaults.
    #
    # Appearance should come primarily from source colors,
    # not from a glossy preview material.
    # -----------------------------------------------------

    if (
        "Metallic"
        in principled.inputs
    ):
        principled.inputs[
            "Metallic"
        ].default_value = (
            0.0
        )

    if (
        "Roughness"
        in principled.inputs
    ):
        principled.inputs[
            "Roughness"
        ].default_value = (
            0.65
        )

    # -----------------------------------------------------
    # Color Attribute
    # -----------------------------------------------------

    color_node = None

    try:
        color_node = nodes.new(
            "ShaderNodeVertexColor"
        )

        color_node.layer_name = (
            attribute_name
        )

    except RuntimeError:
        # Generic attribute fallback in case Blender removes
        # the dedicated vertex-color shader node in a future
        # release.
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
# Apply material projection
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
) -> MaterialProjectionStats:
    """
    Project all source images onto one generated mesh.

    IMPORTANT:

    Call this while obj.data is still in native voxel
    coordinates.

    Do it BEFORE scale_object_to_height() or any arbitrary
    mesh transform which changes the reconstruction-space
    coordinates.

    Uniform object transforms after this function are fine
    because the color attribute is already baked onto the
    mesh corners.

    V1.1 VISIBILITY:

    By default one mesh-local BVH is built once and reused
    for all vertex/view samples.

    A source view contributes only if the sampled point has
    a clear ray toward that orthographic source camera.

    visibility_tester exists primarily for tests and for
    callers which already own a compatible tester.

    If supplied, it is reused instead of building a second
    BVH.
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

    if voxel_size <= 0.0:
        raise ValueError(
            (
                "voxel_size must be "
                "greater than zero."
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
        visibility_tester
        is not None
        and visibility_config
        is not None
    ):
        raise ValueError(
            (
                "visibility_config cannot "
                "be combined with an explicit "
                "visibility_tester."
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
    # Visibility.
    #
    # The BVH must be built ONCE per mesh.
    #
    # Never rebuild it inside the vertex/view loop.
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
    # Compute one color per vertex.
    #
    # We currently use averaged vertex normals, so every
    # corner sharing the same vertex receives the same
    # blended color.
    #
    # The destination remains CORNER because later versions
    # can introduce seam-specific colors without changing
    # the public material representation.
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

    accepted_samples = 0
    rejected_samples = 0

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

        (
            color,
            accepted,
            rejected,
            used_fallback,
        ) = blend_projected_color(
            position,
            normal,
            views,
            width=volume_width,
            depth=volume_depth,
            height=volume_height,
            voxel_size=voxel_size,
            center_xy=center_xy,
            facing_power=facing_power,
            fallback_color=(
                fallback_color
            ),
            allow_backface_fallback=(
                allow_backface_fallback
            ),
            visibility_tester=(
                active_visibility_tester
            ),
        )

        vertex_colors[
            vertex.index
        ] = color

        accepted_samples += (
            accepted
        )

        rejected_samples += (
            rejected
        )

        if used_fallback:
            fallback_vertices += 1
        else:
            projected_vertices += 1

    # -----------------------------------------------------
    # Convert vertex colors to CORNER colors.
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
    # Material
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

    if (
        material.name
        not in {
            item.name
            for item
            in mesh.materials
            if item is not None
        }
    ):
        mesh.materials.append(
            material
        )

    # Generated reconstruction uses one material.
    for polygon in mesh.polygons:
        polygon.material_index = 0

    mesh.update()

    # -----------------------------------------------------
    # Metadata
    # -----------------------------------------------------

    obj[
        "bpt_material"
    ] = (
        MATERIAL_MODE
        if active_visibility_tester
        is not None
        else LEGACY_MATERIAL_MODE
    )

    obj[
        "bpt_material_views"
    ] = len(
        views
    )

    obj[
        "bpt_material_attribute"
    ] = attribute_name

    obj[
        "bpt_material_projected_vertices"
    ] = projected_vertices

    obj[
        "bpt_material_fallback_vertices"
    ] = fallback_vertices

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

    return MaterialProjectionStats(
        vertex_count=vertex_count,
        loop_count=loop_count,
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
    )