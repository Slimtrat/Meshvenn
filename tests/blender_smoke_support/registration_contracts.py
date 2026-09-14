from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import bpy

from .constants import *
from .support import (
    _load_extension, _operator_available, _operator_callable,
    _operator_rna_class, _panel_rna_class, _parse_arguments,
    _purge_package_modules, _require, _require_close, _section,
    _ui_list_rna_class, _validate_package_tree,
)

# Operators
# =========================================================

def _validate_operators_registered() -> None:
    _section(
        "operators"
    )

    for (
        rna_identifier,
        idname,
    ) in zip(
        EXPECTED_OPERATOR_RNA_IDS,
        EXPECTED_OPERATOR_IDNAMES,
        strict=True,
    ):
        operator_class = (
            _operator_rna_class(
                rna_identifier
            )
        )

        _require(
            operator_class
            is not None,
            (
                "Operator RNA class "
                f"missing: {rna_identifier}"
            ),
        )

        _require(
            operator_class.bl_idname
            == idname,
            (
                "Operator id mismatch.\n"
                f"Expected: {idname}\n"
                f"Actual: "
                f"{operator_class.bl_idname}"
            ),
        )

        _require(
            _operator_available(
                idname
            ),
            (
                "bpy.ops operator "
                f"unavailable: {idname}"
            ),
        )

    print(
        "Operators: OK"
    )


# =========================================================
# UI
# =========================================================

def _validate_ui_registered() -> None:
    _section(
        "ui"
    )

    panel = (
        _panel_rna_class(
            MAIN_PANEL_RNA_ID
        )
    )

    _require(
        panel is not None,
        (
            "Meshvenn panel "
            "not registered."
        ),
    )

    _require(
        panel.bl_idname
        == MAIN_PANEL_RNA_ID,
        (
            "Unexpected panel bl_idname."
        ),
    )

    _require(
        panel.bl_space_type
        == "VIEW_3D",
        (
            "Meshvenn panel must "
            "use VIEW_3D."
        ),
    )

    _require(
        panel.bl_region_type
        == "UI",
        (
            "Meshvenn panel must "
            "use UI region."
        ),
    )

    _require(
        panel.bl_category
        == "Meshvenn",
        (
            "Meshvenn panel category "
            "is incorrect."
        ),
    )

    ui_list = (
        _ui_list_rna_class(
            PROJECTION_UI_LIST_RNA_ID
        )
    )

    _require(
        ui_list is not None,
        (
            "Projection UIList "
            "not registered."
        ),
    )

    _require(
        callable(
            getattr(
                ui_list,
                "draw_item",
                None,
            )
        ),
        (
            "Projection UIList "
            "missing draw_item()."
        ),
    )

    print(
        "UI registration: OK"
    )


# =========================================================
# Unregistration
# =========================================================

def _validate_unregistered_state(
    package_name: str,
) -> None:
    _section(
        "unregister"
    )

    _require(
        not hasattr(
            bpy.types.Scene,
            "bpt_settings",
        ),
        (
            "Scene.bpt_settings still "
            "exists after unregister()."
        ),
    )

    for identifier in (
        EXPECTED_OPERATOR_RNA_IDS
    ):
        _require(
            _operator_rna_class(
                identifier
            )
            is None,
            (
                "Operator still registered: "
                f"{identifier}"
            ),
        )

    _require(
        _panel_rna_class(
            MAIN_PANEL_RNA_ID
        )
        is None,
        (
            "Main panel still registered."
        ),
    )

    _require(
        _ui_list_rna_class(
            PROJECTION_UI_LIST_RNA_ID
        )
        is None,
        (
            "Projection UIList "
            "still registered."
        ),
    )

    registry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_registry"
            )
        )
    )

    _require(
        len(
            registry_module
            .PIPELINE_REGISTRY
        )
        == 0,
        (
            "Built-ins remain in registry "
            "after unregister()."
        ),
    )

    implementations_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations"
            )
        )
    )

    _require(
        implementations_module
        .registered_builtin_ids()
        == (),
        (
            "Built-in tracking "
            "was not cleared."
        ),
    )

    print(
        "Unregister: OK"
    )
