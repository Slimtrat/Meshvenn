from __future__ import annotations

import traceback
from pathlib import Path

import bpy

from .blender_data import (_cleanup_datablock, _create_test_mesh, _remove_named_mesh, _remove_named_object)
from .core_bake import _run_core_bake
from .material_validation import _validate_blender_material
from .package_loading import _import_package, _validate_package_tree
from .support import _parse_arguments, _section
from .texture_validation import (_validate_blender_image, _validate_texture_buffer)
from .triangle_adapter import _validate_triangle_adapter

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
