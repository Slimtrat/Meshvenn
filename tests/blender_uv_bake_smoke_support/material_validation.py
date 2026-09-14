from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import Any

import bpy

from .constants import *
from .support import (_clamp01, _purge_package_modules, _quantize_unorm8, _require, _require_close, _require_rgba8_close, _section)

# =========================================================
# Blender Material
# =========================================================

def _validate_blender_material(
    implementation_module,
    obj,
    image,
    uv_layer,
):
    _section(
        "Blender material"
    )

    material = (
        implementation_module
        ._create_baked_material(
            obj,
            image=image,
            uv_layer_name=(
                uv_layer.name
            ),
        )
    )

    implementation_module._assign_material(
        obj,
        material,
    )

    _require(
        material.use_nodes,
        (
            "UV Bake material must "
            "use nodes."
        ),
    )

    _require(
        len(
            obj.data.materials
        )
        == 1,
        (
            "Test mesh should have exactly "
            "one assigned material."
        ),
    )

    _require(
        obj.data.materials[
            0
        ]
        == material,
        (
            "Generated UV Bake material "
            "was not assigned to the mesh."
        ),
    )

    node_tree = (
        material.node_tree
    )

    _require(
        node_tree is not None,
        (
            "Generated material has no "
            "node tree."
        ),
    )

    image_nodes = [
        node
        for node
        in node_tree.nodes
        if (
            node.bl_idname
            == "ShaderNodeTexImage"
        )
    ]

    _require(
        len(
            image_nodes
        )
        == 1,
        (
            "Generated material must contain "
            "exactly one Image Texture node."
        ),
    )

    image_node = (
        image_nodes[
            0
        ]
    )

    _require(
        image_node.image
        == image,
        (
            "Image Texture node does not "
            "reference the baked image."
        ),
    )

    uv_nodes = [
        node
        for node
        in node_tree.nodes
        if (
            node.bl_idname
            == "ShaderNodeUVMap"
        )
    ]

    _require(
        len(
            uv_nodes
        )
        == 1,
        (
            "Generated material must contain "
            "exactly one UV Map node."
        ),
    )

    _require(
        uv_nodes[
            0
        ].uv_map
        == uv_layer.name,
        (
            "UV Map node references "
            "the wrong UV layer."
        ),
    )

    principled_nodes = [
        node
        for node
        in node_tree.nodes
        if (
            node.bl_idname
            == "ShaderNodeBsdfPrincipled"
        )
    ]

    _require(
        len(
            principled_nodes
        )
        == 1,
        (
            "Generated material must contain "
            "exactly one Principled BSDF."
        ),
    )

    principled = (
        principled_nodes[
            0
        ]
    )

    output_nodes = [
        node
        for node
        in node_tree.nodes
        if (
            node.bl_idname
            == "ShaderNodeOutputMaterial"
        )
    ]

    _require(
        len(
            output_nodes
        )
        == 1,
        (
            "Generated material must contain "
            "exactly one Material Output."
        ),
    )

    output = (
        output_nodes[
            0
        ]
    )

    # -----------------------------------------------------
    # Verify graph connectivity, not merely node presence.
    # -----------------------------------------------------

    image_color_output = (
        image_node.outputs.get(
            "Color"
        )
    )

    base_color_input = (
        principled.inputs.get(
            "Base Color"
        )
    )

    bsdf_output = (
        principled.outputs.get(
            "BSDF"
        )
    )

    surface_input = (
        output.inputs.get(
            "Surface"
        )
    )

    uv_output = (
        uv_nodes[
            0
        ].outputs.get(
            "UV"
        )
    )

    vector_input = (
        image_node.inputs.get(
            "Vector"
        )
    )

    _require(
        image_color_output
        is not None,
        (
            "Image Texture has no "
            "Color output."
        ),
    )

    _require(
        base_color_input
        is not None,
        (
            "Principled BSDF has no "
            "Base Color input."
        ),
    )

    _require(
        bsdf_output
        is not None,
        (
            "Principled BSDF has no "
            "BSDF output."
        ),
    )

    _require(
        surface_input
        is not None,
        (
            "Material Output has no "
            "Surface input."
        ),
    )

    _require(
        uv_output
        is not None,
        (
            "UV Map node has no "
            "UV output."
        ),
    )

    _require(
        vector_input
        is not None,
        (
            "Image Texture has no "
            "Vector input."
        ),
    )

    def has_link(
        source_socket,
        destination_socket,
    ) -> bool:
        return any(
            (
                link.from_socket
                == source_socket
                and link.to_socket
                == destination_socket
            )
            for link
            in node_tree.links
        )

    _require(
        has_link(
            uv_output,
            vector_input,
        ),
        (
            "UV Map is not connected "
            "to Image Texture Vector."
        ),
    )

    _require(
        has_link(
            image_color_output,
            base_color_input,
        ),
        (
            "Image Texture Color is not "
            "connected to Base Color."
        ),
    )

    _require(
        has_link(
            bsdf_output,
            surface_input,
        ),
        (
            "Principled BSDF is not "
            "connected to Material Output."
        ),
    )

    print(
        "Blender material: OK"
    )

    print(
        (
            "  material: "
            f"{material.name}"
        )
    )

    print(
        (
            "  image:    "
            f"{image.name}"
        )
    )

    print(
        (
            "  UV map:   "
            f"{uv_layer.name}"
        )
    )

    print(
        "  graph:     UV → Image → Principled → Output"
    )

    return material
