from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

from .arguments import parse_args
from .scene import clear_scene, import_glb, imported_material_summary, print_material_summary, center_objects, ensure_preview_material, validate_preserved_materials
from .camera import create_camera, setup_lighting, setup_render
from .render import render_views, build_contact_sheet

def render_turntable(
    input_path: Path,
    output_dir: Path,
    *,
    views: int,
    size: int,
    samples: int,
    keep_stills: bool,
    preserve_material: bool,
) -> Path:
    """
    Reusable entry point for both:

        visual_preview.yml
        material comparison

    Existing callers get the historical neutral renderer
    when preserve_material=False.

    Material diagnostics use preserve_material=True.
    """

    if not (
        4
        <= views
        <= 16
    ):
        raise ValueError(
            (
                "views must be "
                "between 4 and 16"
            )
        )

    if size < 128:
        raise ValueError(
            "size must be >= 128"
        )

    if samples < 1:
        raise ValueError(
            "samples must be >= 1"
        )

    input_path = (
        input_path.resolve()
    )

    output_dir = (
        output_dir.resolve()
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    clear_scene()

    objects = (
        import_glb(
            input_path
        )
    )

    material_summary = (
        imported_material_summary(
            objects
        )
    )

    print_material_summary(
        material_summary
    )

    if preserve_material:
        validate_preserved_materials(
            objects
        )

        print(
            (
                "Material mode: "
                "PRESERVE IMPORTED"
            )
        )

    else:
        ensure_preview_material(
            objects
        )

        print(
            (
                "Material mode: "
                "NEUTRAL PREVIEW OVERRIDE"
            )
        )

    (
        target,
        model_size,
    ) = (
        center_objects(
            objects
        )
    )

    camera = (
        create_camera(
            target=target,
            model_size=model_size,
        )
    )

    setup_lighting(
        model_size
    )

    setup_render(
        size=size,
        samples=samples,
    )

    stills = (
        render_views(
            camera=camera,
            target=target,
            model_size=model_size,
            output_dir=output_dir,
            views=views,
        )
    )

    contact_path = (
        output_dir
        / "contact_sheet.png"
    )

    build_contact_sheet(
        stills,
        contact_path,
    )

    if not contact_path.exists():
        raise RuntimeError(
            (
                "Contact sheet was "
                "not generated."
            )
        )

    if not keep_stills:
        stills_dir = (
            output_dir
            / "stills"
        )

        if stills_dir.exists():
            shutil.rmtree(
                stills_dir
            )

    return (
        contact_path
    )


# =========================================================
# Main
# =========================================================

def main() -> None:
    args = (
        parse_args()
    )

    contact_path = (
        render_turntable(
            args.input,
            args.output,
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
            preserve_material=(
                args.preserve_material
            ),
        )
    )

    print(
        (
            "Visual preview generated: "
            f"{contact_path}"
        )
    )
