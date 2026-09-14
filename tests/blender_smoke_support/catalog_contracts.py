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
# Built-in catalog
# =========================================================

def _validate_builtin_catalog(
    package_name: str,
) -> None:
    _section(
        "built-in catalog"
    )

    module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations"
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

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    _require(
        module.registered_builtin_ids()
        == EXPECTED_IMPLEMENTATIONS,
        (
            "Unexpected built-in "
            "implementation catalog."
        ),
    )

    _require(
        module
        .builtin_implementation_count()
        == 5,
        (
            "Built-in implementation "
            "count must be 5."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.INPUT
        )
        == "projection-images",
        (
            "Incorrect INPUT default."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.GEOMETRY
        )
        == "native-visual-hull",
        (
            "SDF accidentally replaced "
            "the GEOMETRY default."
        ),
    )

    _require(
        module.builtin_default_id(
            PipelineStage.MATERIAL
        )
        == "projected-color-v1.2",
        (
            "UV Bake accidentally replaced "
            "the MATERIAL default."
        ),
    )

    print(
        "Built-in catalog: OK"
    )

    print(
        "  5 implementations"
    )

    print(
        "  GEOMETRY default preserved"
    )


# =========================================================
