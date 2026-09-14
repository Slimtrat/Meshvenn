from __future__ import annotations

import traceback
from pathlib import Path

from .catalog_contracts import _validate_builtin_catalog
from .core_contracts import (_validate_geometry_contract_core, _validate_sdf_core, _validate_uv_bake_core)
from .material_compatibility import _validate_generic_geometry_material_compatibility
from .property_contracts import (_validate_pipeline_defaults, _validate_projection_defaults, _validate_scene_properties)
from .registration_contracts import (_validate_operators_registered, _validate_ui_registered, _validate_unregistered_state)
from .registry_contracts import _validate_registry
from .sdf_pipeline import (_validate_sdf_default_alignment, _validate_sdf_pipeline_selection)
from .sdf_properties import _validate_sdf_properties
from .support import _parse_arguments, _section, _validate_package_tree, _load_extension
from .uv_bake_contracts import (_validate_uv_bake_default_alignment, _validate_uv_bake_properties)

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

    module = None
    package_name = None
    registered = False

    try:
        # -------------------------------------------------
        # Actual distributable package
        # -------------------------------------------------

        _validate_package_tree(
            package_root
        )

        (
            module,
            package_name,
        ) = (
            _load_extension(
                package_root
            )
        )

        # -------------------------------------------------
        # Pure packaged core
        # -------------------------------------------------

        _validate_geometry_contract_core(
            package_name
        )

        _validate_sdf_core(
            package_name
        )

        _validate_uv_bake_core(
            package_name
        )

        # -------------------------------------------------
        # Register extension
        # -------------------------------------------------

        _section(
            "register extension"
        )

        module.register()

        registered = True

        print(
            "register(): OK"
        )

        # -------------------------------------------------
        # Blender state
        # -------------------------------------------------

        settings = (
            _validate_scene_properties(
                package_name
            )
        )

        _validate_projection_defaults(
            settings
        )

        _validate_pipeline_defaults(
            settings
        )

        # SDF
        _validate_sdf_properties(
            settings
        )

        _validate_sdf_default_alignment(
            package_name,
            settings,
        )

        _validate_registry(
            package_name
        )

        _validate_sdf_pipeline_selection(
            package_name,
            settings,
        )

        # UV Bake
        _validate_uv_bake_properties(
            settings
        )

        _validate_uv_bake_default_alignment(
            package_name,
            settings,
        )

        # Generic architecture guarantee
        _validate_generic_geometry_material_compatibility(
            package_name,
            settings,
        )

        _validate_builtin_catalog(
            package_name
        )

        _validate_operators_registered()

        _validate_ui_registered()

        # -------------------------------------------------
        # Unregister
        # -------------------------------------------------

        module.unregister()

        registered = False

        _validate_unregistered_state(
            package_name
        )

    except Exception:
        print()
        print("=" * 72)
        print(
            "MESHVENN BLENDER SMOKE: FAILED"
        )
        print("=" * 72)
        print()

        traceback.print_exc()

        if (
            registered
            and module is not None
        ):
            try:
                module.unregister()

            except Exception:
                print()
                print(
                    "Cleanup after failure failed:"
                )
                traceback.print_exc()

        raise SystemExit(
            1
        )

    print()
    print("=" * 72)
    print(
        "MESHVENN BLENDER SMOKE: SUCCESS"
    )
    print("=" * 72)
