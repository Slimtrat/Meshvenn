from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from .config import Variant
from .matrix import build_comparison_matrix
from .render import render_variant
from .variants import load_variant, validate_geometry_parity, write_json

# =========================================================
# One sheet
# =========================================================

def process_sheet(
    comparison_root: Path,
    *,
    sheet: str,
    profiles: list[str],
    implementations: list[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    print()

    print(
        "=" * 72
    )

    print(
        (
            "MATERIAL COMPARISON | "
            f"{sheet}"
        )
    )

    print(
        "=" * 72
    )

    sheet_root = (
        comparison_root
        / sheet
    )

    result: dict[
        str,
        Any,
    ] = {
        "sheet": sheet,

        "profiles": list(
            profiles
        ),

        "implementations": list(
            implementations
        ),

        "views": (
            args.views
        ),

        "size": (
            args.size
        ),

        "samples": (
            args.samples
        ),

        "variants": {},

        "errors": [],
    }

    rendered_cells: dict[
        tuple[
            str,
            str,
        ],
        Path,
    ] = {}

    # -----------------------------------------------------
    # Each profile must use identical geometry across all
    # MATERIAL implementations.
    # -----------------------------------------------------

    for profile in (
        profiles
    ):
        variants: list[
            Variant
        ] = []

        for implementation in (
            implementations
        ):
            try:
                variant = (
                    load_variant(
                        comparison_root,
                        sheet=sheet,
                        profile=profile,
                        implementation=(
                            implementation
                        ),
                    )
                )

                variants.append(
                    variant
                )

            except Exception as exc:
                result[
                    "errors"
                ].append(
                    {
                        "profile": profile,

                        "implementation": (
                            implementation
                        ),

                        "phase": (
                            "load"
                        ),

                        "type": (
                            type(
                                exc
                            ).__name__
                        ),

                        "error": str(
                            exc
                        ),
                    }
                )

                if (
                    not args
                    .continue_on_error
                ):
                    raise

        if variants:
            try:
                validate_geometry_parity(
                    variants
                )

            except Exception as exc:
                result[
                    "errors"
                ].append(
                    {
                        "profile": profile,

                        "phase": (
                            "geometry-parity"
                        ),

                        "type": (
                            type(
                                exc
                            ).__name__
                        ),

                        "error": str(
                            exc
                        ),
                    }
                )

                if (
                    not args
                    .continue_on_error
                ):
                    raise

                continue

        # -------------------------------------------------
        # Render each implementation using the same:
        #
        # views
        # size
        # Cycles samples
        # renderer
        # lighting
        # material preservation
        # -------------------------------------------------

        for variant in (
            variants
        ):
            key = (
                profile,
                variant.implementation,
            )

            started_at = (
                time.perf_counter()
            )

            try:
                contact_path = (
                    render_variant(
                        variant,
                        views=(
                            args.views
                        ),
                        size=(
                            args.size
                        ),
                        samples=(
                            args.samples
                        ),
                        keep_stills=(
                            args.keep_stills
                        ),
                        reuse_render=(
                            args.reuse_renders
                        ),
                    )
                )

                elapsed = (
                    time.perf_counter()
                    - started_at
                )

                rendered_cells[
                    key
                ] = contact_path

                result[
                    "variants"
                ][
                    (
                        f"{profile}/"
                        f"{variant.implementation}"
                    )
                ] = {
                    "generated": True,

                    "model": str(
                        variant.model_path
                    ),

                    "variant_manifest": str(
                        variant
                        .manifest_path
                    ),

                    "contact_sheet": str(
                        contact_path
                    ),

                    "elapsed_seconds": (
                        elapsed
                    ),
                }

            except Exception as exc:
                elapsed = (
                    time.perf_counter()
                    - started_at
                )

                result[
                    "variants"
                ][
                    (
                        f"{profile}/"
                        f"{variant.implementation}"
                    )
                ] = {
                    "generated": False,

                    "elapsed_seconds": (
                        elapsed
                    ),

                    "error": str(
                        exc
                    ),
                }

                result[
                    "errors"
                ].append(
                    {
                        "profile": profile,

                        "implementation": (
                            variant
                            .implementation
                        ),

                        "phase": (
                            "render"
                        ),

                        "type": (
                            type(
                                exc
                            ).__name__
                        ),

                        "error": str(
                            exc
                        ),
                    }
                )

                if (
                    not args
                    .continue_on_error
                ):
                    raise

    # -----------------------------------------------------
    # Build the large side-by-side board.
    # -----------------------------------------------------

    matrix_path = (
        sheet_root
        / "material_comparison.png"
    )

    matrix_info = (
        build_comparison_matrix(
            rendered_cells,

            profiles=profiles,

            implementations=(
                implementations
            ),

            output_path=(
                matrix_path
            ),

            gutter=(
                args.gutter
            ),
        )
    )

    result[
        "matrix"
    ] = (
        matrix_info
    )

    result[
        "success"
    ] = (
        len(
            result[
                "errors"
            ]
        )
        == 0
    )

    result_path = (
        sheet_root
        / "render_comparison.json"
    )

    write_json(
        result_path,
        result,
    )

    print()

    print(
        (
            "Comparison matrix: "
            f"{matrix_path}"
        )
    )

    print(
        (
            "Layout manifest: "
            f"{result_path}"
        )
    )

    return result
