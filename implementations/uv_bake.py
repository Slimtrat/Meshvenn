from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

import bpy

from ..core.material_blend import MaterialBlendConfig
from ..core.material_visibility import MeshVisibilityTester
from ..core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..core.projected_material import (
    DEFAULT_FALLBACK_COLOR,
    blend_projected_color,
)
from ..core.uv_bake import (
    SurfaceColorSample,
    UVBakeConfig,
    UVBakeResult,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
)

from .native_visual_hull import (
    NativeVisualHullOutput,
    require_native_visual_hull_output,
)


# =========================================================
# Constants
# =========================================================

IMPLEMENTATION_ID = "uv-bake-v2"

MATERIAL_MODE = "uv-bake-v2"

DEFAULT_TEXTURE_SIZE = 1024

DEFAULT_PADDING_PIXELS = 8

DEFAULT_SAMPLES_PER_AXIS = 1

DEFAULT_UV_LAYER_NAME = "MeshvennUV"

DEFAULT_ISLAND_MARGIN = 0.02

DEFAULT_ANGLE_LIMIT_DEGREES = 66.0

DEFAULT_REUSE_EXISTING_UV = False

DEFAULT_ENABLE_VISIBILITY = True

DEFAULT_ALLOW_BACKFACE_FALLBACK = True

DEFAULT_MIN_FACING = 0.10

DEFAULT_FACING_POWER = 2.0

DEFAULT_RELATIVE_SCORE_CUTOFF = 0.20

DEFAULT_MAX_CONTRIBUTORS = 3

DEFAULT_WEIGHT_POWER = 1.5

DEFAULT_ROUGHNESS = 0.65


# =========================================================
# Configuration
# =========================================================

@dataclass(frozen=True)
class UVBakeMaterialConfig:
    texture_size: int = DEFAULT_TEXTURE_SIZE

    padding_pixels: int = DEFAULT_PADDING_PIXELS

    samples_per_axis: int = DEFAULT_SAMPLES_PER_AXIS

    uv_layer_name: str = DEFAULT_UV_LAYER_NAME

    island_margin: float = DEFAULT_ISLAND_MARGIN

    angle_limit_degrees: float = (
        DEFAULT_ANGLE_LIMIT_DEGREES
    )

    reuse_existing_uv: bool = (
        DEFAULT_REUSE_EXISTING_UV
    )

    enable_visibility: bool = (
        DEFAULT_ENABLE_VISIBILITY
    )

    allow_backface_fallback: bool = (
        DEFAULT_ALLOW_BACKFACE_FALLBACK
    )

    min_facing: float = (
        DEFAULT_MIN_FACING
    )

    facing_power: float = (
        DEFAULT_FACING_POWER
    )

    relative_score_cutoff: float = (
        DEFAULT_RELATIVE_SCORE_CUTOFF
    )

    max_contributors: int = (
        DEFAULT_MAX_CONTRIBUTORS
    )

    weight_power: float = (
        DEFAULT_WEIGHT_POWER
    )

    def validate(self) -> None:
        if self.texture_size <= 0:
            raise ValueError(
                "Texture size must be positive."
            )

        if (
            not self.uv_layer_name
            or not self.uv_layer_name.strip()
        ):
            raise ValueError(
                "UV layer name cannot be empty."
            )

        if (
            not math.isfinite(
                self.island_margin
            )
            or self.island_margin < 0.0
            or self.island_margin > 1.0
        ):
            raise ValueError(
                "Island margin must be in [0, 1]."
            )

        if (
            not math.isfinite(
                self.angle_limit_degrees
            )
            or self.angle_limit_degrees <= 0.0
            or self.angle_limit_degrees > 90.0
        ):
            raise ValueError(
                (
                    "Smart-project angle limit must "
                    "be inside ]0, 90]."
                )
            )

        self.to_bake_config().validate()

        self.to_blend_config().validate()

    def to_bake_config(self) -> UVBakeConfig:
        return UVBakeConfig(
            width=self.texture_size,
            height=self.texture_size,
            padding_pixels=self.padding_pixels,
            samples_per_axis=(
                self.samples_per_axis
            ),
            background_color=(
                0.0,
                0.0,
                0.0,
                0.0,
            ),
            clamp_colors=True,
        )

    def to_blend_config(
        self,
    ) -> MaterialBlendConfig:
        return MaterialBlendConfig(
            min_facing=self.min_facing,
            facing_power=self.facing_power,
            relative_score_cutoff=(
                self.relative_score_cutoff
            ),
            max_contributors=(
                self.max_contributors
            ),
            weight_power=self.weight_power,
        )


# =========================================================
# Pipeline output
# =========================================================

@dataclass(frozen=True)
class UVBakeMaterialOutput:
    """
    MATERIAL-stage result.

    Geometry is not duplicated.

    The same Blender object receives:

        UV map
        image texture
        Principled material
    """

    blender_object: bpy.types.Object

    geometry: NativeVisualHullOutput

    image: bpy.types.Image

    material: bpy.types.Material

    uv_layer_name: str

    bake_result: UVBakeResult

    config: UVBakeMaterialConfig

    @property
    def texture_size(self) -> int:
        return self.config.texture_size

    @property
    def covered_pixels(self) -> int:
        return (
            self.bake_result
            .stats
            .covered_pixels
        )

    @property
    def padded_pixels(self) -> int:
        return (
            self.bake_result
            .stats
            .padded_pixels
        )

    @property
    def coverage_ratio(self) -> float:
        return (
            self.bake_result
            .stats
            .coverage_ratio
        )


# =========================================================
# Context
# =========================================================

def _resolve_settings(
    context: PipelineContext,
) -> Any:
    if context.settings is not None:
        return context.settings

    if context.scene is None:
        return None

    return getattr(
        context.scene,
        "bpt_settings",
        None,
    )


def require_uv_bake_output(
    context: PipelineContext,
) -> UVBakeMaterialOutput:
    output = context.require_output(
        PipelineStage.MATERIAL
    )

    if not isinstance(
        output,
        UVBakeMaterialOutput,
    ):
        raise TypeError(
            (
                "MATERIAL output is not "
                "UVBakeMaterialOutput. "
                f"Received {type(output).__name__}."
            )
        )

    return output


# =========================================================
# Optional setting reader
#
# These properties do not all exist in properties.py yet.
# Until they are added, V2 runs with stable defaults.
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


def _config_from_settings(
    settings: Any,
) -> UVBakeMaterialConfig:
    config = UVBakeMaterialConfig(
        texture_size=int(
            _read_setting(
                settings,
                "uv_bake_texture_size",
                DEFAULT_TEXTURE_SIZE,
            )
        ),
        padding_pixels=int(
            _read_setting(
                settings,
                "uv_bake_padding_pixels",
                DEFAULT_PADDING_PIXELS,
            )
        ),
        samples_per_axis=int(
            _read_setting(
                settings,
                "uv_bake_samples_per_axis",
                DEFAULT_SAMPLES_PER_AXIS,
            )
        ),
        uv_layer_name=str(
            _read_setting(
                settings,
                "uv_bake_uv_layer_name",
                DEFAULT_UV_LAYER_NAME,
            )
        ).strip(),
        island_margin=float(
            _read_setting(
                settings,
                "uv_bake_island_margin",
                DEFAULT_ISLAND_MARGIN,
            )
        ),
        angle_limit_degrees=float(
            _read_setting(
                settings,
                "uv_bake_angle_limit_degrees",
                DEFAULT_ANGLE_LIMIT_DEGREES,
            )
        ),
        reuse_existing_uv=bool(
            _read_setting(
                settings,
                "uv_bake_reuse_existing_uv",
                DEFAULT_REUSE_EXISTING_UV,
            )
        ),
        enable_visibility=bool(
            _read_setting(
                settings,
                "material_enable_visibility",
                DEFAULT_ENABLE_VISIBILITY,
            )
        ),
        allow_backface_fallback=bool(
            _read_setting(
                settings,
                "material_allow_backface_fallback",
                DEFAULT_ALLOW_BACKFACE_FALLBACK,
            )
        ),
        min_facing=float(
            _read_setting(
                settings,
                "material_min_facing",
                DEFAULT_MIN_FACING,
            )
        ),
        facing_power=float(
            _read_setting(
                settings,
                "material_facing_power",
                DEFAULT_FACING_POWER,
            )
        ),
        relative_score_cutoff=float(
            _read_setting(
                settings,
                "material_relative_score_cutoff",
                DEFAULT_RELATIVE_SCORE_CUTOFF,
            )
        ),
        max_contributors=int(
            _read_setting(
                settings,
                "material_max_contributors",
                DEFAULT_MAX_CONTRIBUTORS,
            )
        ),
        weight_power=float(
            _read_setting(
                settings,
                "material_weight_power",
                DEFAULT_WEIGHT_POWER,
            )
        ),
    )

    config.validate()

    return config


# =========================================================
# Geometry validation
# =========================================================

def _validate_geometry(
    geometry: NativeVisualHullOutput,
) -> None:
    obj = geometry.blender_object

    if obj is None:
        raise ValueError(
            "Geometry object is missing."
        )

    if obj.type != "MESH":
        raise TypeError(
            "UV Bake requires a mesh object."
        )

    mesh = obj.data

    if mesh is None:
        raise ValueError(
            "Geometry mesh data is missing."
        )

    mesh.update()

    if len(mesh.vertices) == 0:
        raise ValueError(
            "Geometry contains no vertices."
        )

    if len(mesh.polygons) == 0:
        raise ValueError(
            "Geometry contains no polygons."
        )

    if len(mesh.loops) == 0:
        raise ValueError(
            "Geometry contains no loops."
        )

    if not geometry.source.material_views:
        raise ValueError(
            (
                "No source material views "
                "are available."
            )
        )


# =========================================================
# UV generation
# =========================================================

def _ensure_named_uv_layer(
    mesh: bpy.types.Mesh,
    name: str,
):
    layer = mesh.uv_layers.get(
        name
    )

    if layer is None:
        layer = mesh.uv_layers.new(
            name=name,
            do_init=False,
        )

    mesh.uv_layers.active = layer

    try:
        layer.active_render = True

    except Exception:
        pass

    return layer


def _restore_object_selection(
    view_layer,
    previous_active,
    previous_selected,
    previous_mode: str,
) -> None:
    try:
        current_active = (
            view_layer.objects.active
        )

        if (
            current_active is not None
            and current_active.mode
            != "OBJECT"
        ):
            bpy.ops.object.mode_set(
                mode="OBJECT"
            )

    except Exception:
        pass

    for item in view_layer.objects:
        try:
            item.select_set(False)
        except Exception:
            pass

    for item in previous_selected:
        try:
            if item.name in view_layer.objects:
                item.select_set(True)
        except Exception:
            pass

    try:
        if (
            previous_active is not None
            and previous_active.name
            in view_layer.objects
        ):
            view_layer.objects.active = (
                previous_active
            )

            if previous_mode != "OBJECT":
                bpy.ops.object.mode_set(
                    mode=previous_mode
                )

    except Exception:
        pass


def _smart_project_uv(
    obj: bpy.types.Object,
    *,
    uv_layer_name: str,
    island_margin: float,
    angle_limit_degrees: float,
):
    """
    Create/rebuild the UV map using Blender Smart Project.

    Selection and active-object state are restored after the
    operation so pipeline execution does not unnecessarily
    disturb the user's scene.
    """

    mesh = obj.data

    view_layer = (
        bpy.context.view_layer
    )

    if view_layer is None:
        raise RuntimeError(
            (
                "No Blender view layer is "
                "available for UV unwrap."
            )
        )

    previous_active = (
        view_layer.objects.active
    )

    previous_selected = tuple(
        item
        for item
        in view_layer.objects
        if item.select_get()
    )

    previous_mode = (
        previous_active.mode
        if previous_active is not None
        else "OBJECT"
    )

    try:
        if (
            previous_active is not None
            and previous_active.mode
            != "OBJECT"
        ):
            bpy.ops.object.mode_set(
                mode="OBJECT"
            )

        for item in view_layer.objects:
            try:
                item.select_set(False)
            except Exception:
                pass

        obj.select_set(
            True
        )

        view_layer.objects.active = obj

        uv_layer = (
            _ensure_named_uv_layer(
                mesh,
                uv_layer_name,
            )
        )

        bpy.ops.object.mode_set(
            mode="EDIT"
        )

        bpy.ops.mesh.select_all(
            action="SELECT"
        )

        result = (
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(
                    angle_limit_degrees
                ),
                margin_method="FRACTION",
                island_margin=(
                    island_margin
                ),
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=True,
            )
        )

        if "FINISHED" not in result:
            raise RuntimeError(
                (
                    "Blender Smart UV Project "
                    f"returned {result}."
                )
            )

        bpy.ops.object.mode_set(
            mode="OBJECT"
        )

        mesh.update()

        resolved_layer = (
            mesh.uv_layers.get(
                uv_layer.name
            )
        )

        if resolved_layer is None:
            raise RuntimeError(
                (
                    "Smart UV Project completed "
                    "without a UV layer."
                )
            )

        mesh.uv_layers.active = (
            resolved_layer
        )

        try:
            resolved_layer.active_render = (
                True
            )
        except Exception:
            pass

        return resolved_layer

    finally:
        _restore_object_selection(
            view_layer,
            previous_active,
            previous_selected,
            previous_mode,
        )


def _resolve_uv_layer(
    obj: bpy.types.Object,
    config: UVBakeMaterialConfig,
):
    mesh = obj.data

    if config.reuse_existing_uv:
        layer = mesh.uv_layers.active

        if layer is None:
            raise ValueError(
                (
                    "Reuse Existing UV is enabled "
                    "but the mesh has no UV map."
                )
            )

        try:
            layer.active_render = True
        except Exception:
            pass

        return layer

    return _smart_project_uv(
        obj,
        uv_layer_name=(
            config.uv_layer_name
        ),
        island_margin=(
            config.island_margin
        ),
        angle_limit_degrees=(
            config.angle_limit_degrees
        ),
    )


# =========================================================
# Blender mesh -> pure UV bake triangles
# =========================================================

def _vector3_tuple(
    value,
) -> tuple[
    float,
    float,
    float,
]:
    return (
        float(value[0]),
        float(value[1]),
        float(value[2]),
    )


def _vector2_tuple(
    value,
) -> tuple[
    float,
    float,
]:
    return (
        float(value[0]),
        float(value[1]),
    )


def _corner_normal(
    mesh: bpy.types.Mesh,
    *,
    loop_index: int,
    vertex_index: int,
    polygon_index: int,
) -> tuple[
    float,
    float,
    float,
]:
    # -----------------------------------------------------
    # Blender 5.x corner normals.
    # -----------------------------------------------------

    try:
        if (
            mesh.corner_normals
            and loop_index
            < len(mesh.corner_normals)
        ):
            normal = (
                mesh.corner_normals[
                    loop_index
                ].vector
            )

            if normal.length_squared > 1e-12:
                return _vector3_tuple(
                    normal
                )

    except Exception:
        pass

    # -----------------------------------------------------
    # Vertex normal fallback.
    # -----------------------------------------------------

    try:
        normal = (
            mesh.vertex_normals[
                vertex_index
            ].vector
        )

        if normal.length_squared > 1e-12:
            return _vector3_tuple(
                normal
            )

    except Exception:
        pass

    # -----------------------------------------------------
    # Polygon normal fallback.
    # -----------------------------------------------------

    try:
        normal = (
            mesh.polygon_normals[
                polygon_index
            ].vector
        )

        if normal.length_squared > 1e-12:
            return _vector3_tuple(
                normal
            )

    except Exception:
        pass

    raise ValueError(
        (
            "Could not resolve a valid "
            f"surface normal for loop "
            f"{loop_index}."
        )
    )


def _read_uv(
    uv_layer,
    loop_index: int,
) -> tuple[
    float,
    float,
]:
    """
    Blender 5.x exposes MeshUVLoopLayer.uv.

    data[] remains as a compatibility fallback.
    """

    try:
        value = (
            uv_layer.uv[
                loop_index
            ].vector
        )

        return _vector2_tuple(
            value
        )

    except Exception:
        value = (
            uv_layer.data[
                loop_index
            ].uv
        )

        return _vector2_tuple(
            value
        )


def _build_uv_triangles(
    obj: bpy.types.Object,
    uv_layer,
) -> tuple[
    UVBakeTriangle,
    ...
]:
    mesh = obj.data

    mesh.update()

    mesh.calc_loop_triangles()

    triangles: list[
        UVBakeTriangle
    ] = []

    for loop_triangle in (
        mesh.loop_triangles
    ):
        loop_indices = tuple(
            int(index)
            for index
            in loop_triangle.loops
        )

        if len(loop_indices) != 3:
            continue

        vertices: list[
            UVBakeVertex
        ] = []

        for loop_index in (
            loop_indices
        ):
            loop = (
                mesh.loops[
                    loop_index
                ]
            )

            vertex_index = int(
                loop.vertex_index
            )

            vertex = (
                mesh.vertices[
                    vertex_index
                ]
            )

            vertices.append(
                UVBakeVertex(
                    position=(
                        _vector3_tuple(
                            vertex.co
                        )
                    ),
                    normal=(
                        _corner_normal(
                            mesh,
                            loop_index=(
                                loop_index
                            ),
                            vertex_index=(
                                vertex_index
                            ),
                            polygon_index=(
                                int(
                                    loop_triangle
                                    .polygon_index
                                )
                            ),
                        )
                    ),
                    uv=(
                        _read_uv(
                            uv_layer,
                            loop_index,
                        )
                    ),
                )
            )

        triangles.append(
            UVBakeTriangle(
                a=vertices[0],
                b=vertices[1],
                c=vertices[2],
                source_index=int(
                    loop_triangle
                    .polygon_index
                ),
            )
        )

    if not triangles:
        raise ValueError(
            (
                "Mesh triangulation produced "
                "no UV triangles."
            )
        )

    return tuple(
        triangles
    )


# =========================================================
# Projected Color sampler
# =========================================================

def _build_surface_sampler(
    geometry: NativeVisualHullOutput,
    config: UVBakeMaterialConfig,
):
    views = list(
        geometry
        .source
        .material_views
    )

    if not views:
        raise ValueError(
            (
                "No projection images are "
                "available for texture bake."
            )
        )

    blend_config = (
        config.to_blend_config()
    )

    visibility_tester = None

    if config.enable_visibility:
        # -------------------------------------------------
        # Critical performance point:
        #
        # build one BVH for the COMPLETE bake.
        #
        # Never rebuild visibility per texel.
        # -------------------------------------------------

        visibility_tester = (
            MeshVisibilityTester
            .from_blender_object(
                geometry.blender_object
            )
        )

    def sample_surface(
        position,
        normal,
    ) -> SurfaceColorSample:
        (
            color,
            accepted_samples,
            _rejected_samples,
            used_fallback,
        ) = (
            blend_projected_color(
                position,
                normal,
                views,
                width=(
                    geometry.volume.width
                ),
                depth=(
                    geometry.volume.depth
                ),
                height=(
                    geometry.volume.height
                ),
                voxel_size=(
                    geometry.voxel_size
                ),
                center_xy=(
                    geometry.center_xy
                ),
                facing_power=(
                    config.facing_power
                ),
                fallback_color=(
                    DEFAULT_FALLBACK_COLOR
                ),
                allow_backface_fallback=(
                    config
                    .allow_backface_fallback
                ),
                visibility_tester=(
                    visibility_tester
                ),
                blend_config=(
                    blend_config
                ),
            )
        )

        return SurfaceColorSample(
            color=color,
            used_fallback=(
                used_fallback
            ),
            selected_samples=(
                accepted_samples
            ),
        )

    return sample_surface


# =========================================================
# Blender image
# =========================================================

def _create_baked_image(
    obj: bpy.types.Object,
    result: UVBakeResult,
) -> bpy.types.Image:
    name = (
        f"{obj.name} UV Bake V2"
    )

    image = (
        bpy.data.images.new(
            name=name,
            width=(
                result.texture.width
            ),
            height=(
                result.texture.height
            ),
            alpha=True,
            float_buffer=False,
        )
    )

    try:
        image.pixels.foreach_set(
            result.texture.pixels
        )

        image.update()

        # Pack the generated texture into the .blend so the
        # result does not immediately depend on an external
        # file.
        image.pack()

    except Exception:
        bpy.data.images.remove(
            image
        )

        raise

    return image


# =========================================================
# Blender material
# =========================================================

def _create_baked_material(
    obj: bpy.types.Object,
    *,
    image: bpy.types.Image,
    uv_layer_name: str,
) -> bpy.types.Material:
    material = (
        bpy.data.materials.new(
            name=(
                f"{obj.name} UV Material V2"
            )
        )
    )

    try:
        material.use_nodes = True

        node_tree = (
            material.node_tree
        )

        if node_tree is None:
            raise RuntimeError(
                (
                    "Could not create Blender "
                    "material node tree."
                )
            )

        nodes = (
            node_tree.nodes
        )

        links = (
            node_tree.links
        )

        nodes.clear()

        # -------------------------------------------------
        # UV map
        # -------------------------------------------------

        uv_node = nodes.new(
            "ShaderNodeUVMap"
        )

        uv_node.name = (
            "Meshvenn UV Map"
        )

        uv_node.label = (
            uv_layer_name
        )

        uv_node.uv_map = (
            uv_layer_name
        )

        uv_node.location = (
            -600.0,
            0.0,
        )

        # -------------------------------------------------
        # Image
        # -------------------------------------------------

        image_node = nodes.new(
            "ShaderNodeTexImage"
        )

        image_node.name = (
            "Meshvenn UV Bake"
        )

        image_node.label = (
            "UV Bake V2"
        )

        image_node.image = image

        image_node.interpolation = (
            "Linear"
        )

        image_node.extension = (
            "EXTEND"
        )

        image_node.location = (
            -350.0,
            0.0,
        )

        # -------------------------------------------------
        # Principled
        # -------------------------------------------------

        principled = nodes.new(
            "ShaderNodeBsdfPrincipled"
        )

        principled.name = (
            "Meshvenn Principled"
        )

        principled.label = (
            "UV Bake V2"
        )

        principled.location = (
            0.0,
            0.0,
        )

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
            ].default_value = (
                DEFAULT_ROUGHNESS
            )

        # -------------------------------------------------
        # Output
        # -------------------------------------------------

        output = nodes.new(
            "ShaderNodeOutputMaterial"
        )

        output.name = (
            "Meshvenn Material Output"
        )

        output.location = (
            350.0,
            0.0,
        )

        # -------------------------------------------------
        # Connections
        # -------------------------------------------------

        links.new(
            uv_node.outputs[
                "UV"
            ],
            image_node.inputs[
                "Vector"
            ],
        )

        links.new(
            image_node.outputs[
                "Color"
            ],
            principled.inputs[
                "Base Color"
            ],
        )

        links.new(
            principled.outputs[
                "BSDF"
            ],
            output.inputs[
                "Surface"
            ],
        )

    except Exception:
        bpy.data.materials.remove(
            material
        )

        raise

    return material


def _assign_material(
    obj: bpy.types.Object,
    material: bpy.types.Material,
) -> None:
    mesh = obj.data

    mesh.materials.clear()

    mesh.materials.append(
        material
    )


# =========================================================
# Metadata
# =========================================================

def _write_metadata(
    obj: bpy.types.Object,
    output: UVBakeMaterialOutput,
) -> None:
    stats = (
        output
        .bake_result
        .stats
    )

    obj[
        "meshvenn_material_implementation"
    ] = IMPLEMENTATION_ID

    obj[
        "meshvenn_material_version"
    ] = "2"

    obj[
        "meshvenn_material_mode"
    ] = MATERIAL_MODE

    obj[
        "meshvenn_uv_layer"
    ] = (
        output.uv_layer_name
    )

    obj[
        "meshvenn_uv_bake_image"
    ] = (
        output.image.name
    )

    obj[
        "meshvenn_uv_bake_material"
    ] = (
        output.material.name
    )

    obj[
        "meshvenn_uv_bake_texture_size"
    ] = (
        output.config.texture_size
    )

    obj[
        "meshvenn_uv_bake_padding"
    ] = (
        output.config.padding_pixels
    )

    obj[
        "meshvenn_uv_bake_samples_per_axis"
    ] = (
        output.config
        .samples_per_axis
    )

    obj[
        "meshvenn_uv_bake_triangles"
    ] = (
        stats.triangle_count
    )

    obj[
        "meshvenn_uv_bake_covered_pixels"
    ] = (
        stats.covered_pixels
    )

    obj[
        "meshvenn_uv_bake_padded_pixels"
    ] = (
        stats.padded_pixels
    )

    obj[
        "meshvenn_uv_bake_overlap_pixels"
    ] = (
        stats.overlap_pixels
    )

    obj[
        "meshvenn_uv_bake_surface_samples"
    ] = (
        stats.surface_samples
    )

    obj[
        "meshvenn_uv_bake_fallback_samples"
    ] = (
        stats.fallback_samples
    )

    obj[
        "meshvenn_uv_bake_coverage_ratio"
    ] = float(
        stats.coverage_ratio
    )


# =========================================================
# UI hook
# =========================================================

def _draw_optional_property(
    layout,
    settings,
    property_name: str,
    label: str,
) -> bool:
    if not hasattr(
        settings,
        property_name,
    ):
        return False

    layout.prop(
        settings,
        property_name,
        text=label,
    )

    return True


# =========================================================
# Implementation
# =========================================================

class UVBakeImplementation:
    """
    Built-in MATERIAL implementation.

    Projection Images
            ↓
    Native Visual Hull
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
    """

    _descriptor = (
        ImplementationDescriptor(
            identifier=(
                IMPLEMENTATION_ID
            ),
            stage=(
                PipelineStage.MATERIAL
            ),
            label="UV Bake V2",
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
            ),
        )
    )

    @property
    def descriptor(
        self,
    ) -> ImplementationDescriptor:
        return self._descriptor

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
                require_native_visual_hull_output(
                    context
                )
            )

            _validate_geometry(
                geometry
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
                    )
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
                    )
                )
            )

        return (
            ImplementationAvailability
            .ready_state(
                details={
                    "object": (
                        geometry
                        .blender_object
                        .name
                    ),
                    "views": (
                        len(
                            geometry
                            .source
                            .material_views
                        )
                    ),
                    "texture_size": (
                        config.texture_size
                    ),
                    "padding_pixels": (
                        config.padding_pixels
                    ),
                    "samples_per_axis": (
                        config.samples_per_axis
                    ),
                    "reuse_existing_uv": (
                        config
                        .reuse_existing_uv
                    ),
                }
            )
        )

    # -----------------------------------------------------
    # Optional generic UI hook
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
                    f"Texture Size: "
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
                    f"Padding: "
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
                    f"{DEFAULT_SAMPLES_PER_AXIS}×"
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
            "Island Margin",
        )

        _draw_optional_property(
            uv_box,
            settings,
            "uv_bake_angle_limit_degrees",
            "Angle Limit",
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

        try:
            geometry = (
                require_native_visual_hull_output(
                    context
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.MATERIAL
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "Geometry unavailable: "
                        f"{exc}"
                    ),
                )
            )

        try:
            _validate_geometry(
                geometry
            )

            config = (
                _config_from_settings(
                    settings
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.MATERIAL
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "Invalid UV Bake V2 "
                        f"configuration: {exc}"
                    ),
                )
            )

        obj = (
            geometry.blender_object
        )

        # -------------------------------------------------
        # 1. UV unwrap
        # -------------------------------------------------

        uv_layer = (
            _resolve_uv_layer(
                obj,
                config,
            )
        )

        # -------------------------------------------------
        # 2. Blender mesh -> pure bake triangles
        # -------------------------------------------------

        triangles = (
            _build_uv_triangles(
                obj,
                uv_layer,
            )
        )

        # -------------------------------------------------
        # 3. Projected Color V1.2 surface sampler
        # -------------------------------------------------

        sampler = (
            _build_surface_sampler(
                geometry,
                config,
            )
        )

        # -------------------------------------------------
        # 4. Pure UV bake
        # -------------------------------------------------

        window_manager = getattr(
            bpy.context,
            "window_manager",
            None,
        )

        if window_manager is not None:
            try:
                window_manager.progress_begin(
                    0,
                    len(triangles),
                )
            except Exception:
                window_manager = None

        def progress_callback(
            progress,
        ) -> None:
            if window_manager is None:
                return

            try:
                window_manager.progress_update(
                    progress
                    .completed_triangles
                )
            except Exception:
                pass

        try:
            bake_result = (
                bake_uv_texture(
                    triangles,
                    sampler,
                    config=(
                        config
                        .to_bake_config()
                    ),
                    progress_callback=(
                        progress_callback
                    ),
                )
            )

        finally:
            if window_manager is not None:
                try:
                    window_manager.progress_end()
                except Exception:
                    pass

        if (
            bake_result
            .stats
            .covered_pixels
            <= 0
        ):
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.MATERIAL
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "UV bake produced no "
                        "covered texels."
                    ),
                    metadata={
                        "triangles": (
                            len(triangles)
                        ),
                    },
                )
            )

        # -------------------------------------------------
        # 5. Blender image
        # -------------------------------------------------

        image = (
            _create_baked_image(
                obj,
                bake_result,
            )
        )

        material = None

        try:
            # ---------------------------------------------
            # 6. Portable Blender material
            # ---------------------------------------------

            material = (
                _create_baked_material(
                    obj,
                    image=image,
                    uv_layer_name=(
                        uv_layer.name
                    ),
                )
            )

            _assign_material(
                obj,
                material,
            )

            output = (
                UVBakeMaterialOutput(
                    blender_object=obj,
                    geometry=geometry,
                    image=image,
                    material=material,
                    uv_layer_name=(
                        uv_layer.name
                    ),
                    bake_result=(
                        bake_result
                    ),
                    config=config,
                )
            )

            _write_metadata(
                obj,
                output,
            )

        except Exception:
            if (
                material is not None
                and material.users == 0
            ):
                bpy.data.materials.remove(
                    material
                )

            if image.users == 0:
                bpy.data.images.remove(
                    image
                )

            raise

        stats = (
            bake_result.stats
        )

        context.metadata[
            "material_mode"
        ] = MATERIAL_MODE

        context.metadata[
            "uv_bake_image"
        ] = image.name

        context.metadata[
            "uv_bake_material"
        ] = material.name

        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    PipelineStage.MATERIAL
                ),
                implementation_id=(
                    IMPLEMENTATION_ID
                ),
                payload=output,
                message=(
                    "UV texture baked: "
                    f"{config.texture_size}×"
                    f"{config.texture_size}, "
                    f"{stats.covered_pixels} "
                    "covered texels."
                ),
                metrics={
                    "triangles": (
                        stats.triangle_count
                    ),
                    "rasterized_triangles": (
                        stats
                        .rasterized_triangles
                    ),
                    "degenerate_triangles": (
                        stats
                        .degenerate_triangles
                    ),
                    "texture_size": (
                        config.texture_size
                    ),
                    "covered_pixels": (
                        stats.covered_pixels
                    ),
                    "padded_pixels": (
                        stats.padded_pixels
                    ),
                    "overlap_pixels": (
                        stats.overlap_pixels
                    ),
                    "surface_samples": (
                        stats.surface_samples
                    ),
                    "fallback_samples": (
                        stats.fallback_samples
                    ),
                    "selected_source_samples": (
                        stats
                        .selected_source_samples
                    ),
                    "coverage_ratio": (
                        stats.coverage_ratio
                    ),
                },
                metadata={
                    "object_name": obj.name,
                    "image_name": image.name,
                    "material_name": (
                        material.name
                    ),
                    "uv_layer": (
                        uv_layer.name
                    ),
                    "texture_width": (
                        bake_result
                        .texture
                        .width
                    ),
                    "texture_height": (
                        bake_result
                        .texture
                        .height
                    ),
                    "padding_pixels": (
                        config.padding_pixels
                    ),
                    "samples_per_axis": (
                        config
                        .samples_per_axis
                    ),
                    "visibility": (
                        config
                        .enable_visibility
                    ),
                    "reuse_existing_uv": (
                        config
                        .reuse_existing_uv
                    ),
                },
            )
        )