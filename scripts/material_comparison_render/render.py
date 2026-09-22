from __future__ import annotations

import shutil
import time
from pathlib import Path

from scripts.render_turntable import render_turntable

from .config import Variant

# =========================================================
# Render one variant
# =========================================================

def render_variant(
    variant: Variant,
    *,
    views: int,
    size: int,
    samples: int,
    keep_stills: bool,
    reuse_render: bool,
) -> Path:
    if (
        reuse_render
        and variant
        .contact_sheet_path
        .is_file()
    ):
        print(
            (
                "Reuse render: "
                f"{variant.contact_sheet_path}"
            )
        )

        return (
            variant
            .contact_sheet_path
        )

    if variant.render_root.exists():
        shutil.rmtree(
            variant.render_root
        )

    variant.render_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()

    print(
        "-" * 72
    )

    print(
        (
            f"{variant.sheet} / "
            f"{variant.profile} / "
            f"{variant.implementation}"
        )
    )

    print(
        "-" * 72
    )

    started_at = (
        time.perf_counter()
    )

    contact_path = (
        render_turntable(
            variant.model_path,
            variant.render_root,

            views=views,

            size=size,

            samples=samples,

            keep_stills=(
                keep_stills
            ),

            # Critical:
            #
            # do NOT replace the MATERIAL implementation
            # with the neutral geometry-preview material.
            preserve_material=True,
        )
    )

    elapsed = (
        time.perf_counter()
        - started_at
    )

    if not contact_path.is_file():
        raise RuntimeError(
            (
                "Variant render did not "
                "produce a contact sheet: "
                f"{contact_path}"
            )
        )

    print(
        (
            "Variant rendered in "
            f"{elapsed:.3f}s"
        )
    )

    return contact_path
