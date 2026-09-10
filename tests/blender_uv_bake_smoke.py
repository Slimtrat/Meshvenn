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
    tolerance: float = (
        FLOAT_TOLERANCE
    ),
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


def _purge_package_modules(
    package_name: str,
) -> None:
    prefix = (
        package_name
        + "."
    )

    modules = [
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
        modules,
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

    parent_string = str(
        package_parent
    )

    if (
        parent_string
        not in sys.path
    ):
        sys.path.insert(
            0,
            parent_string,
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
            if (
                datablock.name
                in bpy.data.materials
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
            if (
                datablock.name
                in bpy.data.images
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
            if (
                datablock.name
                in bpy.data.objects
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
            if (
                datablock.name
                in bpy.data.meshes
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
    Blender 5.x exposes the UV attribute through:

        uv_layer.uv[index].vector

    Older API versions expose:

        uv_layer.data[index].uv

    Keep the smoke compatible with both representations.
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
    # Unit square in XY.
    #
    # Geometry deliberately matches UV coordinates:
    #
    #     position.x == uv.u
    #     position.y == uv.v
    #
    # This makes the synthetic sampler trivial to verify.
    #
    #        3 -------- 2
    #        |        / |
    #        |      /   |
    #        |    /     |
    #        |  /       |
    #        |/         |
    #        0 -------- 1
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

    # -----------------------------------------------------
    # One UV per loop.
    #
    # Since every vertex coordinate already lies inside
    # [0,1], position.xy maps directly to UV.
    # -----------------------------------------------------

    for loop in mesh.loops:
        vertex = (
            mesh.vertices[
                loop.vertex_index
            ]
        )

        uv = (
            float(
                vertex.co.x
            ),
            float(
                vertex.co.y
            ),
        )

        _set_loop_uv(
            uv_layer,
            loop.index,
            uv,
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
            "Test mesh should contain "
            "4 vertices."
        ),
    )

    _require(
        len(
            mesh.polygons
        )
        == 2,
        (
            "Test mesh should contain "
            "2 polygons."
        ),
    )

    _require(
        len(
            mesh.loops
        )
        == 6,
        (
            "Test mesh should contain "
            "6 loops."
        ),
    )

    print(
        "Mesh: OK"
    )

    print(
        f"  vertices: {len(mesh.vertices)}"
    )

    print(
        f"  polygons: {len(mesh.polygons)}"
    )

    print(
        f"  loops:    {len(mesh.loops)}"
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
            "Expected two triangulated "
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

            normal = (
                vertex.normal
            )

            _require_close(
                normal[0],
                0.0,
                message=(
                    "Unexpected normal X."
                ),
            )

            _require_close(
                normal[1],
                0.0,
                message=(
                    "Unexpected normal Y."
                ),
            )

            _require_close(
                normal[2],
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
# Pure UV bake
# =========================================================

def _run_core_bake(
    uv_bake_module,
    triangles,
):
    _section(
        "core bake"
    )

    # -----------------------------------------------------
    # Synthetic surface shader:
    #
    #     R = X
    #     G = Y
    #     B = 0.25
    #     A = 1
    #
    # Since position XY == UV, texture coordinates have a
    # directly predictable color.
    # -----------------------------------------------------

    def sampler(
        position,
        normal,
    ):
        _require_close(
            normal[0],
            0.0,
            message=(
                "Sampler received invalid normal X."
            ),
        )

        _require_close(
            normal[1],
            0.0,
            message=(
                "Sampler received invalid normal Y."
            ),
        )

        _require_close(
            normal[2],
            1.0,
            message=(
                "Sampler received invalid normal Z."
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

    config = (
        uv_bake_module
        .UVBakeConfig(
            width=(
                TEXTURE_SIZE
            ),
            height=(
                TEXTURE_SIZE
            ),
            padding_pixels=0,
            samples_per_axis=1,
        )
    )

    result = (
        uv_bake_module
        .bake_uv_texture(
            triangles,
            sampler,
            config=config,
        )
    )

    stats = (
        result.stats
    )

    _require(
        stats.triangle_count == 2,
        (
            "Unexpected bake triangle count."
        ),
    )

    _require(
        stats.rasterized_triangles == 2,
        (
            "Both test triangles should "
            "rasterize."
        ),
    )

    _require(
        stats.degenerate_triangles == 0,
        (
            "No test triangle should "
            "be degenerate."
        ),
    )

    _require(
        stats.covered_pixels
        == (
            TEXTURE_SIZE
            * TEXTURE_SIZE
        ),
        (
            "Full square UV map should cover "
            "the complete texture.\n"
            f"Expected: "
            f"{TEXTURE_SIZE * TEXTURE_SIZE}\n"
            f"Actual:   "
            f"{stats.covered_pixels}"
        ),
    )

    _require(
        stats.padded_pixels == 0,
        (
            "Padding should be disabled "
            "for this smoke."
        ),
    )

    _require(
        stats.surface_samples
        >= stats.covered_pixels,
        (
            "Surface sample count cannot be "
            "smaller than covered texels."
        ),
    )

    _require(
        stats.selected_source_samples
        == (
            stats.surface_samples
            * 2
        ),
        (
            "SurfaceColorSample diagnostics "
            "were not accumulated correctly."
        ),
    )

    _require(
        stats.fallback_samples == 0,
        (
            "Synthetic sampler must not "
            "report fallback samples."
        ),
    )

    _require(
        stats.coverage_ratio == 1.0,
        (
            "Full-square UV bake should have "
            "100% coverage."
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
# Texture validation
# =========================================================

def _expected_coordinate(
    pixel: int,
) -> float:
    return (
        (
            float(
                pixel
            )
            + 0.5
        )
        / float(
            TEXTURE_SIZE
        )
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
    ) in (
        test_pixels
    ):
        color = (
            result
            .texture
            .rgba(
                x,
                y,
            )
        )

        expected_u = (
            _expected_coordinate(
                x
            )
        )

        expected_v = (
            _expected_coordinate(
                y
            )
        )

        _require_close(
            color[0],
            expected_u,
            message=(
                f"Unexpected red at ({x}, {y})."
            ),
        )

        _require_close(
            color[1],
            expected_v,
            message=(
                f"Unexpected green at ({x}, {y})."
            ),
        )

        _require_close(
            color[2],
            0.25,
            message=(
                f"Unexpected blue at ({x}, {y})."
            ),
        )

        _require_close(
            color[3],
            1.0,
            message=(
                f"Unexpected alpha at ({x}, {y})."
            ),
        )

        _require(
            result.is_covered(
                x,
                y,
            ),
            (
                "Expected texel is not "
                f"covered: ({x}, {y})"
            ),
        )

    print(
        "TextureBuffer colors: OK"
    )


# =========================================================
# Blender image
# =========================================================

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
    # Check the bottom-left pixel copied from TextureBuffer.
    # -----------------------------------------------------

    pixel = (
        image.pixels
    )

    expected = (
        _expected_coordinate(
            0
        ),
        _expected_coordinate(
            0
        ),
        0.25,
        1.0,
    )

    for channel in range(
        4
    ):
        _require_close(
            pixel[
                channel
            ],
            expected[
                channel
            ],
            message=(
                "Blender image pixel buffer "
                f"mismatch at channel {channel}."
            ),
        )

    print(
        "Blender image: OK"
    )

    print(
        f"  name: {image.name}"
    )

    print(
        (
            "  size: "
            f"{image.size[0]}×"
            f"{image.size[1]}"
        )
    )

    return image


# =========================================================
# Blender material
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
            "UV Bake material must use nodes."
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
            "was not assigned to mesh."
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
        if node.bl_idname
        == "ShaderNodeTexImage"
    ]

    _require(
        len(
            image_nodes
        )
        == 1,
        (
            "Generated material should contain "
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
        if node.bl_idname
        == "ShaderNodeUVMap"
    ]

    _require(
        len(
            uv_nodes
        )
        == 1,
        (
            "Generated material should contain "
            "exactly one UV Map node."
        ),
    )

    _require(
        uv_nodes[
            0
        ].uv_map
        == uv_layer.name,
        (
            "UV Map node references the "
            "wrong UV layer."
        ),
    )

    principled_nodes = [
        node
        for node
        in node_tree.nodes
        if node.bl_idname
        == "ShaderNodeBsdfPrincipled"
    ]

    _require(
        len(
            principled_nodes
        )
        == 1,
        (
            "Generated material should contain "
            "exactly one Principled BSDF."
        ),
    )

    output_nodes = [
        node
        for node
        in node_tree.nodes
        if node.bl_idname
        == "ShaderNodeOutputMaterial"
    ]

    _require(
        len(
            output_nodes
        )
        == 1,
        (
            "Generated material should contain "
            "exactly one Material Output."
        ),
    )

    _require(
        len(
            node_tree.links
        )
        >= 3,
        (
            "UV Bake material node graph "
            "is incomplete."
        ),
    )

    print(
        "Blender material: OK"
    )

    print(
        f"  material: {material.name}"
    )

    print(
        f"  image:    {image.name}"
    )

    print(
        f"  UV map:   {uv_layer.name}"
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
        # Package
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

        _require(
            callable(
                getattr(
                    uv_bake_module,
                    "bake_uv_texture",
                    None,
                )
            ),
            (
                "Packaged UV bake core "
                "is incomplete."
            ),
        )

        _require(
            callable(
                getattr(
                    implementation_module,
                    "_build_uv_triangles",
                    None,
                )
            ),
            (
                "UV Bake Blender triangle "
                "adapter is missing."
            ),
        )

        _require(
            callable(
                getattr(
                    implementation_module,
                    "_create_baked_image",
                    None,
                )
            ),
            (
                "UV Bake Blender image "
                "adapter is missing."
            ),
        )

        _require(
            callable(
                getattr(
                    implementation_module,
                    "_create_baked_material",
                    None,
                )
            ),
            (
                "UV Bake Blender material "
                "adapter is missing."
            ),
        )

        print(
            "Packaged UV Bake modules: OK"
        )

        # -------------------------------------------------
        # Blender test mesh.
        # -------------------------------------------------

        (
            obj,
            mesh,
            uv_layer,
        ) = (
            _create_test_mesh()
        )

        # -------------------------------------------------
        # Blender mesh -> pure core representation.
        # -------------------------------------------------

        triangles = (
            _validate_triangle_adapter(
                implementation_module,
                obj,
                uv_layer,
            )
        )

        # -------------------------------------------------
        # Pure rasterizer.
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
        # TextureBuffer -> Blender image.
        # -------------------------------------------------

        image = (
            _validate_blender_image(
                implementation_module,
                obj,
                result,
            )
        )

        # -------------------------------------------------
        # Image -> Blender material.
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
        # Explicitly clean everything created by the smoke.
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