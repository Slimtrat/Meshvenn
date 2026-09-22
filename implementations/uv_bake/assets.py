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
for _dependency in (_dependency_0, _dependency_1, _dependency_2, _dependency_3, _dependency_4, _dependency_5, _dependency_6,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

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
                result
                .texture
                .width
            ),

            height=(
                result
                .texture
                .height
            ),

            alpha=True,

            # Portable RGBA8 image.
            float_buffer=False,
        )
    )

    try:
        image.pixels.foreach_set(
            result.texture.pixels
        )

        image.update()

        # Keep generated texture embedded in .blend and
        # available to glTF export.

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
                f"{obj.name} "
                "UV Material V2"
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

        # UV.

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

        # Image texture.

        image_node = nodes.new(
            "ShaderNodeTexImage"
        )

        image_node.name = (
            "Meshvenn UV Bake"
        )

        image_node.label = (
            "UV Bake V2"
        )

        image_node.image = (
            image
        )

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

        # Principled BSDF.

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

        # Material output.

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

        # Connections.

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
