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

# =========================================================
# Registry
# =========================================================

def _validate_registry(
    package_name: str,
) -> None:
    _section(
        "pipeline registry"
    )

    registry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_registry"
            )
        )
    )

    contracts_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_contracts"
            )
        )
    )

    registry = (
        registry_module
        .PIPELINE_REGISTRY
    )

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    actual_ids = (
        registry
        .implementation_ids()
    )

    _require(
        actual_ids
        == EXPECTED_IMPLEMENTATIONS,
        (
            "Unexpected registered "
            "implementations.\n"
            f"Expected: {EXPECTED_IMPLEMENTATIONS}\n"
            f"Actual:   {actual_ids}"
        ),
    )

    expected_defaults = {
        PipelineStage.INPUT:
            "projection-images",

        PipelineStage.GEOMETRY:
            "native-visual-hull",

        PipelineStage.MATERIAL:
            "projected-color-v1.2",

        PipelineStage.RIG:
            "canonical-biped-v1",

        PipelineStage.EXPORT:
            None,
    }

    for (
        stage,
        expected,
    ) in (
        expected_defaults.items()
    ):
        actual = (
            registry.default_id(
                stage
            )
        )

        _require(
            actual == expected,
            (
                "Unexpected registry default "
                f"for {stage.value}.\n"
                f"Expected: {expected!r}\n"
                f"Actual:   {actual!r}"
            ),
        )

    # -----------------------------------------------------
    # SDF
    # -----------------------------------------------------

    sdf = (
        registry.require(
            "sdf-reconstruction-v1",
            stage=(
                PipelineStage.GEOMETRY
            ),
        )
    )

    sdf_descriptor = (
        sdf.descriptor
    )

    _require(
        sdf_descriptor.identifier
        == "sdf-reconstruction-v1",
        (
            "Unexpected SDF "
            "implementation id."
        ),
    )

    _require(
        sdf_descriptor.stage
        == PipelineStage.GEOMETRY,
        (
            "SDF must belong "
            "to GEOMETRY."
        ),
    )

    _require(
        sdf_descriptor.label
        == "SDF Reconstruction V1",
        (
            "Unexpected SDF label."
        ),
    )

    _require(
        sdf_descriptor.experimental,
        (
            "SDF V1 should remain "
            "experimental."
        ),
    )

    for method_name in (
        "execute",
        "availability",
        "draw_settings",
    ):
        _require(
            callable(
                getattr(
                    sdf,
                    method_name,
                    None,
                )
            ),
            (
                "SDF implementation "
                f"missing {method_name}()."
            ),
        )

    # -----------------------------------------------------
    # UV Bake
    # -----------------------------------------------------

    uv_bake = (
        registry.require(
            "uv-bake-v2",
            stage=(
                PipelineStage.MATERIAL
            ),
        )
    )

    _require(
        uv_bake.descriptor.experimental,
        (
            "UV Bake V2 should remain "
            "experimental."
        ),
    )

    print(
        "Registry: OK"
    )

    for implementation_id in (
        actual_ids
    ):
        suffix = ""

        if (
            implementation_id
            == "native-visual-hull"
        ):
            suffix = (
                " [GEOMETRY default]"
            )

        elif (
            implementation_id
            == "sdf-reconstruction-v1"
        ):
            suffix = (
                " [GEOMETRY experimental]"
            )

        elif (
            implementation_id
            == "projected-color-v1.2"
        ):
            suffix = (
                " [MATERIAL default]"
            )

        elif (
            implementation_id
            == "uv-bake-v2"
        ):
            suffix = (
                " [MATERIAL experimental]"
            )

        print(
            (
                f"  OK  "
                f"{implementation_id}"
                f"{suffix}"
            )
        )


# =========================================================
