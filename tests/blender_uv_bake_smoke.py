from __future__ import annotations

import argparse
import importlib
import math
import sys
import traceback

from pathlib import Path
from typing import Any

import bpy


# =========================================================
# Configuration
# =========================================================

DEFAULT_PACKAGE_ROOT = (
    Path("dist")
    / "blender_projection_tool"
)

OBJECT_NAME = (
    "MeshvennUVBakeSmokeObject"
)

MESH_NAME = (
    "MeshvennUVBakeSmokeMesh"
)

UV_LAYER_NAME = (
    "MeshvennUVBakeSmokeUV"
)

TEXTURE_SIZE = 8

FLOAT_TOLERANCE = 1e-5

RGBA8_TOLERANCE = 1e-6


REQUIRED_PACKAGE_FILES = (
    "__init__.py",

    "core/uv_bake.py",

    "implementations/__init__.py",
    "implementations/uv_bake.py",
)


# =========================================================
# CLI
# =========================================================

def _script_arguments(
) -> list[str]:
    if "--" not in sys.argv:
        return []

    separator_index = (
        sys.argv.index(
            "--"
        )
    )

    return sys.argv[
        separator_index + 1:
    ]


def _parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Functional Blender smoke test "
            "for Meshvenn UV Bake V2."
        )
    )

    parser.add_argument(
        "--package-root",
        default=str(
            DEFAULT_PACKAGE_ROOT
        ),
        help=(
            "Path to the unpacked Meshvenn "
            "Blender extension."
        ),
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Generic helpers
# =========================================================

def _section(
    title: str,
) -> None:
    print()

    print(
        "=" * 72
    )

    print(
        f"Meshvenn UV Bake smoke | {title}"
    )

    print(
        "=" * 72
    )


def _require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def _require_close(
    actual: float,
    expected: float,
    *,
    message: str,
    tolerance: float = FLOAT_TOLERANCE,
) -> None:
    if not math.isclose(
        float(actual),
        float(expected),
        rel_tol=tolerance,
        abs_tol=tolerance,
    ):
        raise AssertionError(
            (
                f"{message}\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )
        )


def _clamp01(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(value),
        ),
    )


def _quantize_unorm8(
    value: float,
) -> float:
    """
    Reproduce the expected storage precision of the Blender
    image created by UV Bake V2:

        float_buffer=False

    Example:

        0.0625
            ↓
        round(0.0625 * 255)
            ↓
        16
            ↓
        16 / 255
            ↓
        0.062745098...
    """

    normalized = (
        _clamp01(
            value
        )
    )

    integer = math.floor(
        normalized
        * 255.0
        + 0.5
    )

    integer = max(
        0,
        min(
            255,
            integer,
        ),
    )

    return (
        float(integer)
        / 255.0
    )


def _require_rgba8_close(
    actual: float,
    source_float: float,
    *,
    message: str,
) -> None:
    expected = (
        _quantize_unorm8(
            source_float
        )
    )

    _require_close(
        actual,
        expected,
        message=message,
        tolerance=(
            RGBA8_TOLERANCE
        ),
    )


def _purge_package_modules(
    package_name: str,
) -> None:
    prefix = (
        package_name
        + "."
    )

    names = [
        name
        for name
        in tuple(
            sys.modules.keys()
        )
        if (
            name == package_name
            or name.startswith(
                prefix
            )
        )
    ]

    for name in sorted(
        names,
        key=len,
        reverse=True,
    ):
        sys.modules.pop(
            name,
            None,
        )


# =========================================================
# Package
# =========================================================

def _validate_package_tree(
    package_root: Path,
) -> None:
    _section(
        "package"
    )

    _require(
        package_root.is_dir(),
        (
            "Package root does not exist: "
            f"{package_root}"
        ),
    )

    for relative_path in (
        REQUIRED_PACKAGE_FILES
    ):
        path = (
            package_root
            / relative_path
        )

        _require(
            path.is_file(),
            (
                "Required packaged file "
                f"is missing: {relative_path}"
            ),
        )

        print(
            f"  OK  {relative_path}"
        )


def _import_package(
    package_root: Path,
):
    package_root = (
        package_root.resolve()
    )

    package_name = (
        package_root.name
    )

    package_parent = (
        package_root.parent
    )

    _purge_package_modules(
        package_name
    )

    package_parent_string = str(
        package_parent
    )

    if (
        package_parent_string
        not in sys.path
    ):
        sys.path.insert(
            0,
            package_parent_string,
        )

    package = (
        importlib.import_module(
            package_name
        )
    )

    print(
        f"Package import: {package_name}"
    )

    return (
        package,
        package_name,
    )


# =========================================================
# Cleanup
# =========================================================

def _remove_named_object(
    name: str,
) -> None:
    obj = bpy.data.objects.get(
        name
    )

    if obj is not None:
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )


def _remove_named_mesh(
    name: str,
) -> None:
    mesh = bpy.data.meshes.get(
        name
    )

    if mesh is not None:
        bpy.data.meshes.remove(
            mesh,
            do_unlink=True,
        )


def _cleanup_datablock(
    datablock: Any,
) -> None:
    if datablock is None:
        return

    try:
        if isinstance(
            datablock,
            bpy.types.Material,
        ):
            bpy.data.materials.remove(
                datablock,
                do_unlink=True,
            )

            return

        if isinstance(
            datablock,
            bpy.types.Image,
        ):
            bpy.data.images.remove(
                datablock,
                do_unlink=True,
            )

            return

        if isinstance(
            datablock,
            bpy.types.Object,
        ):
            bpy.data.objects.remove(
                datablock,
                do_unlink=True,
            )

            return

        if isinstance(
            datablock,
            bpy.types.Mesh,
        ):
            bpy.data.meshes.remove(
                datablock,
                do_unlink=True,
            )

    except Exception:
        print(
            (
                "Cleanup warning for "
                f"{type(datablock).__name__}:"
            )
        )

        traceback.print_exc()


# =========================================================
# Blender UV compatibility
# =========================================================

def _set_loop_uv(
    uv_layer,
    loop_index: int,
    uv: tuple[
        float,
        float,
    ],
) -> None:
    """
    Blender 5.x:

        uv_layer.uv[index].vector

    Older fallback:

        uv_layer.data[index].uv
    """

    try:
        uv_layer.uv[
            loop_index
        ].vector = uv

        return

    except Exception:
        pass

    uv_layer.data[
        loop_index
    ].uv = uv


# =========================================================
# Test mesh
# =========================================================

def _create_test_mesh(
) -> tuple[
    bpy.types.Object,
    bpy.types.Mesh,
    Any,
]:
    _section(
        "create Blender mesh"
    )

    _remove_named_object(
        OBJECT_NAME
    )

    _remove_named_mesh(
        MESH_NAME
    )

    mesh = (
        bpy.data.meshes.new(
            MESH_NAME
        )
    )

    # -----------------------------------------------------
    # Geometry deliberately matches UV coordinates:
    #
    #     X == U
    #     Y == V
    #
    #
    #        3 -------- 2
    #        |        / |
    #        |      /   |
    #        |    /     |
    #        |  /       |
    #        |/         |
    #        0 -------- 1
    #
    # -----------------------------------------------------

    vertices = (
        (
            0.0,
            0.0,
            0.0,
        ),
        (
            1.0,
            0.0,
            0.0,
        ),
        (
            1.0,
            1.0,
            0.0,
        ),
        (
            0.0,
            1.0,
            0.0,
        ),
    )

    faces = (
        (
            0,
            1,
            2,
        ),
        (
            0,
            2,
            3,
        ),
    )

    mesh.from_pydata(
        vertices,
        (),
        faces,
    )

    mesh.update()

    obj = (
        bpy.data.objects.new(
            OBJECT_NAME,
            mesh,
        )
    )

    bpy.context.scene.collection.objects.link(
        obj
    )

    uv_layer = (
        mesh.uv_layers.new(
            name=(
                UV_LAYER_NAME
            ),
            do_init=False,
        )
    )

    for loop in mesh.loops:
        vertex = (
            mesh.vertices[
                loop.vertex_index
            ]
        )

        _set_loop_uv(
            uv_layer,
            loop.index,
            (
                float(
                    vertex.co.x
                ),
                float(
                    vertex.co.y
                ),
            ),
        )

    mesh.uv_layers.active = (
        uv_layer
    )

    try:
        uv_layer.active_render = True

    except Exception:
        pass

    mesh.update()

    _require(
        len(
            mesh.vertices
        )
        == 4,
        (
            "Test mesh must contain "
            "4 vertices."
        ),
    )

    _require(
        len(
            mesh.polygons
        )
        == 2,
        (
            "Test mesh must contain "
            "2 polygons."
        ),
    )

    _require(
        len(
            mesh.loops
        )
        == 6,
        (
            "Test mesh must contain "
            "6 loops."
        ),
    )

    print(
        "Mesh: OK"
    )

    print(
        (
            "  vertices: "
            f"{len(mesh.vertices)}"
        )
    )

    print(
        (
            "  polygons: "
            f"{len(mesh.polygons)}"
        )
    )

    print(
        (
            "  loops:    "
            f"{len(mesh.loops)}"
        )
    )

    return (
        obj,
        mesh,
        uv_layer,
    )


# =========================================================
# Blender mesh -> UVBakeTriangle
# =========================================================

def _validate_triangle_adapter(
    implementation_module,
    obj,
    uv_layer,
):
    _section(
        "Blender → UVBakeTriangle"
    )

    triangles = (
        implementation_module
        ._build_uv_triangles(
            obj,
            uv_layer,
        )
    )

    _require(
        len(
            triangles
        )
        == 2,
        (
            "Expected exactly two "
            "UV bake triangles."
        ),
    )

    for (
        triangle_index,
        triangle,
    ) in enumerate(
        triangles
    ):
        _require(
            triangle.absolute_uv_area
            > 0.0,
            (
                "Triangle has zero UV area: "
                f"{triangle_index}"
            ),
        )

        for vertex in (
            triangle.a,
            triangle.b,
            triangle.c,
        ):
            (
                x,
                y,
                z,
            ) = (
                vertex.position
            )

            (
                u,
                v,
            ) = (
                vertex.uv
            )

            _require_close(
                x,
                u,
                message=(
                    "Position X / UV U mismatch."
                ),
            )

            _require_close(
                y,
                v,
                message=(
                    "Position Y / UV V mismatch."
                ),
            )

            _require_close(
                z,
                0.0,
                message=(
                    "Unexpected surface Z."
                ),
            )

            (
                nx,
                ny,
                nz,
            ) = (
                vertex.normal
            )

            _require_close(
                nx,
                0.0,
                message=(
                    "Unexpected normal X."
                ),
            )

            _require_close(
                ny,
                0.0,
                message=(
                    "Unexpected normal Y."
                ),
            )

            _require_close(
                nz,
                1.0,
                message=(
                    "Unexpected normal Z."
                ),
            )

    print(
        "Triangle adapter: OK"
    )

    return triangles


# =========================================================
# Core UV bake
# =========================================================

def _run_core_bake(
    uv_bake_module,
    triangles,
):
    _section(
        "core bake"
    )

    # -----------------------------------------------------
    # Synthetic shader:
    #
    #     R = X
    #     G = Y
    #     B = 0.25
    #     A = 1.0
    #
    # Since X/Y == U/V, texels are deterministic.
    # -----------------------------------------------------

    def sampler(
        position,
        normal,
    ):
        _require_close(
            normal[0],
            0.0,
            message=(
                "Sampler received invalid "
                "normal X."
            ),
        )

        _require_close(
            normal[1],
            0.0,
            message=(
                "Sampler received invalid "
                "normal Y."
            ),
        )

        _require_close(
            normal[2],
            1.0,
            message=(
                "Sampler received invalid "
                "normal Z."
            ),
        )

        return (
            uv_bake_module
            .SurfaceColorSample(
                color=(
                    position[0],
                    position[1],
                    0.25,
                    1.0,
                ),
                used_fallback=False,
                selected_samples=2,
            )
        )

    result = (
        uv_bake_module
        .bake_uv_texture(
            triangles,
            sampler,
            config=(
                uv_bake_module
                .UVBakeConfig(
                    width=TEXTURE_SIZE,
                    height=TEXTURE_SIZE,
                    padding_pixels=0,
                    samples_per_axis=1,
                )
            ),
        )
    )

    stats = (
        result.stats
    )

    _require(
        stats.triangle_count
        == 2,
        (
            "Unexpected triangle count."
        ),
    )

    _require(
        stats.rasterized_triangles
        == 2,
        (
            "Both test triangles "
            "must rasterize."
        ),
    )

    _require(
        stats.degenerate_triangles
        == 0,
        (
            "Test mesh must contain no "
            "degenerate UV triangle."
        ),
    )

    expected_pixels = (
        TEXTURE_SIZE
        * TEXTURE_SIZE
    )

    _require(
        stats.covered_pixels
        == expected_pixels,
        (
            "Unit square UV map should "
            "cover the entire texture.\n"
            f"Expected: {expected_pixels}\n"
            f"Actual:   "
            f"{stats.covered_pixels}"
        ),
    )

    _require(
        stats.padded_pixels
        == 0,
        (
            "Padding must be disabled "
            "for this smoke."
        ),
    )

    _require(
        stats.surface_samples
        >= stats.covered_pixels,
        (
            "Surface sample count cannot "
            "be smaller than coverage."
        ),
    )

    _require(
        stats.selected_source_samples
        == (
            stats.surface_samples
            * 2
        ),
        (
            "SurfaceColorSample selected "
            "sample diagnostics are wrong."
        ),
    )

    _require(
        stats.fallback_samples
        == 0,
        (
            "Synthetic sampler must not "
            "report fallback samples."
        ),
    )

    _require_close(
        stats.coverage_ratio,
        1.0,
        message=(
            "Expected complete UV coverage."
        ),
    )

    print(
        "Core UV bake: OK"
    )

    print(
        (
            "  resolution: "
            f"{result.texture.width}×"
            f"{result.texture.height}"
        )
    )

    print(
        (
            "  covered:    "
            f"{stats.covered_pixels}"
        )
    )

    print(
        (
            "  overlaps:   "
            f"{stats.overlap_pixels}"
        )
    )

    print(
        (
            "  samples:    "
            f"{stats.surface_samples}"
        )
    )

    return result


# =========================================================
# TextureBuffer
# =========================================================

def _expected_coordinate(
    pixel: int,
) -> float:
    return (
        (
            float(pixel)
            + 0.5
        )
        / float(
            TEXTURE_SIZE
        )
    )


def _expected_source_color(
    x: int,
    y: int,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    return (
        _expected_coordinate(
            x
        ),
        _expected_coordinate(
            y
        ),
        0.25,
        1.0,
    )


def _validate_texture_buffer(
    result,
) -> None:
    _section(
        "TextureBuffer"
    )

    test_pixels = (
        (
            0,
            0,
        ),
        (
            3,
            2,
        ),
        (
            4,
            4,
        ),
        (
            7,
            7,
        ),
    )

    for (
        x,
        y,
    ) in test_pixels:
        actual = (
            result
            .texture
            .rgba(
                x,
                y,
            )
        )

        expected = (
            _expected_source_color(
                x,
                y,
            )
        )

        for channel in range(
            4
        ):
            _require_close(
                actual[
                    channel
                ],
                expected[
                    channel
                ],
                message=(
                    "TextureBuffer mismatch "
                    f"at ({x}, {y}), "
                    f"channel {channel}."
                ),
            )

        _require(
            result.is_covered(
                x,
                y,
            ),
            (
                "Expected texel is not "
                f"covered: ({x}, {y})."
            ),
        )

    print(
        "TextureBuffer colors: OK"
    )


# =========================================================
# Blender Image
# =========================================================

def _image_pixel_rgba(
    image: bpy.types.Image,
    x: int,
    y: int,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    width = int(
        image.size[0]
    )

    offset = (
        (
            y
            * width
            + x
        )
        * 4
    )

    return (
        float(
            image.pixels[
                offset
            ]
        ),
        float(
            image.pixels[
                offset + 1
            ]
        ),
        float(
            image.pixels[
                offset + 2
            ]
        ),
        float(
            image.pixels[
                offset + 3
            ]
        ),
    )


def _validate_blender_image(
    implementation_module,
    obj,
    result,
):
    _section(
        "Blender image"
    )

    image = (
        implementation_module
        ._create_baked_image(
            obj,
            result,
        )
    )

    _require(
        int(
            image.size[0]
        )
        == TEXTURE_SIZE,
        (
            "Unexpected Blender image width."
        ),
    )

    _require(
        int(
            image.size[1]
        )
        == TEXTURE_SIZE,
        (
            "Unexpected Blender image height."
        ),
    )

    # -----------------------------------------------------
    # UV Bake V2 deliberately creates:
    #
    #     float_buffer=False
    #
    # The core TextureBuffer is FLOAT32, but the Blender
    # image stores each channel as normalized 8-bit.
    #
    # The smoke therefore verifies the expected UNORM8
    # representation rather than requiring impossible
    # float-exact equality.
    # -----------------------------------------------------

    test_pixels = (
        (
            0,
            0,
        ),
        (
            3,
            2,
        ),
        (
            4,
            4,
        ),
        (
            7,
            7,
        ),
    )

    for (
        x,
        y,
    ) in test_pixels:
        actual = (
            _image_pixel_rgba(
                image,
                x,
                y,
            )
        )

        source = (
            _expected_source_color(
                x,
                y,
            )
        )

        for channel in range(
            4
        ):
            _require_rgba8_close(
                actual[
                    channel
                ],
                source[
                    channel
                ],
                message=(
                    "Blender RGBA8 pixel "
                    "mismatch at "
                    f"({x}, {y}), "
                    f"channel {channel}."
                ),
            )

    # -----------------------------------------------------
    # Explicit regression for the CI failure that motivated
    # this test.
    #
    # Core:
    #
    #     0.0625
    #
    # Blender byte image:
    #
    #     16 / 255
    #     == 0.062745098...
    # -----------------------------------------------------

    bottom_left = (
        _image_pixel_rgba(
            image,
            0,
            0,
        )
    )

    expected_quantized = (
        _quantize_unorm8(
            0.0625
        )
    )

    _require_close(
        bottom_left[0],
        expected_quantized,
        message=(
            "Blender image did not "
            "store expected RGBA8 value."
        ),
        tolerance=(
            RGBA8_TOLERANCE
        ),
    )

    print(
        "Blender image: OK"
    )

    print(
        (
            "  name: "
            f"{image.name}"
        )
    )

    print(
        (
            "  size: "
            f"{image.size[0]}×"
            f"{image.size[1]}"
        )
    )

    print(
        (
            "  source R: "
            "0.062500000"
        )
    )

    print(
        (
            "  stored R: "
            f"{bottom_left[0]:.9f}"
        )
    )

    print(
        (
            "  RGBA8 R: "
            f"{expected_quantized:.9f}"
        )
    )

    return image


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


# =========================================================
# Main
# =========================================================

def main() -> None:
    arguments = (
        _parse_arguments()
    )

    package_root = Path(
        arguments.package_root
    )

    obj = None

    mesh = None

    image = None

    material = None

    try:
        # -------------------------------------------------
        # Validate distributed package.
        # -------------------------------------------------

        _validate_package_tree(
            package_root
        )

        (
            _package,
            package_name,
        ) = (
            _import_package(
                package_root
            )
        )

        # -------------------------------------------------
        # Import packaged V2 modules.
        # -------------------------------------------------

        uv_bake_module = (
            importlib.import_module(
                (
                    f"{package_name}."
                    "core.uv_bake"
                )
            )
        )

        implementation_module = (
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.uv_bake"
                )
            )
        )

        _section(
            "modules"
        )

        required_functions = (
            (
                uv_bake_module,
                "bake_uv_texture",
            ),
            (
                implementation_module,
                "_build_uv_triangles",
            ),
            (
                implementation_module,
                "_create_baked_image",
            ),
            (
                implementation_module,
                "_create_baked_material",
            ),
            (
                implementation_module,
                "_assign_material",
            ),
        )

        for (
            module,
            function_name,
        ) in required_functions:
            _require(
                callable(
                    getattr(
                        module,
                        function_name,
                        None,
                    )
                ),
                (
                    "Required UV Bake function "
                    f"is missing: {function_name}"
                ),
            )

        print(
            "Packaged UV Bake modules: OK"
        )

        # -------------------------------------------------
        # Blender mesh + UVs.
        # -------------------------------------------------

        (
            obj,
            mesh,
            uv_layer,
        ) = (
            _create_test_mesh()
        )

        # -------------------------------------------------
        # Blender → core representation.
        # -------------------------------------------------

        triangles = (
            _validate_triangle_adapter(
                implementation_module,
                obj,
                uv_layer,
            )
        )

        # -------------------------------------------------
        # Pure core bake.
        # -------------------------------------------------

        result = (
            _run_core_bake(
                uv_bake_module,
                triangles,
            )
        )

        _validate_texture_buffer(
            result
        )

        # -------------------------------------------------
        # Core texture → Blender image.
        # -------------------------------------------------

        image = (
            _validate_blender_image(
                implementation_module,
                obj,
                result,
            )
        )

        # -------------------------------------------------
        # Blender image → material graph.
        # -------------------------------------------------

        material = (
            _validate_blender_material(
                implementation_module,
                obj,
                image,
                uv_layer,
            )
        )

    except Exception:
        print()

        print(
            "=" * 72
        )

        print(
            "MESHVENN UV BAKE BLENDER SMOKE: FAILED"
        )

        print(
            "=" * 72
        )

        print()

        traceback.print_exc()

        raise SystemExit(
            1
        )

    finally:
        # -------------------------------------------------
        # Explicit cleanup.
        # -------------------------------------------------

        _cleanup_datablock(
            material
        )

        _cleanup_datablock(
            image
        )

        _cleanup_datablock(
            obj
        )

        _cleanup_datablock(
            mesh
        )

    print()

    print(
        "=" * 72
    )

    print(
        "MESHVENN UV BAKE BLENDER SMOKE: SUCCESS"
    )

    print(
        "=" * 72
    )


if __name__ == "__main__":
    main()