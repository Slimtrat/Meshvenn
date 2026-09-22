from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

from scripts.render_turntable import center_objects, clear_scene, create_camera, ensure_preview_material, import_glb, setup_lighting
from .source import parse_args, load_sheet
from .layout import build_cells, clear_cell
from .camera import common_ortho_scale, configure_projection_render
from .render import render_view, composite_view, save_sheet

def main() -> None:
    args = parse_args()

    if args.samples < 1:
        raise ValueError(
            "samples must be >= 1"
        )

    if args.framing <= 0.0:
        raise ValueError(
            "framing must be > 0"
        )

    input_path = (
        args.input.resolve()
    )

    template_path = (
        args.template.resolve()
    )

    output_path = (
        args.output.resolve()
    )

    stills_dir = (
        output_path.parent
        / (
            output_path.stem
            + "_stills"
        )
    )

    if stills_dir.exists():
        shutil.rmtree(
            stills_dir
        )

    stills_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------
    # Existing render pipeline
    # -----------------------------------------------------

    clear_scene()

    objects = import_glb(
        input_path
    )

    (
        target,
        model_size,
    ) = center_objects(
        objects
    )

    if (
        args.material_mode
        == "neutral"
    ):
        ensure_preview_material(
            objects
        )

    camera = create_camera(
        target=target,
        model_size=model_size,
    )

    setup_lighting(
        model_size
    )

    configure_projection_render(
        samples=args.samples,
    )

    # -----------------------------------------------------
    # Original Projection Tool sheet
    # -----------------------------------------------------

    (
        sheet_pixels,
        sheet_width,
        sheet_height,
    ) = load_sheet(
        template_path
    )

    cells = build_cells(
        sheet_width,
        sheet_height,
    )

    ortho_scale = common_ortho_scale(
        model_size,
        cells,
        framing=args.framing,
    )

    print(
        (
            "Projection sheet: "
            f"{sheet_width}x{sheet_height}"
        )
    )

    print(
        (
            "Common ortho scale: "
            f"{ortho_scale:.4f}"
        )
    )

    # -----------------------------------------------------
    # 000 → BOT
    # -----------------------------------------------------

    for (
        index,
        (
            name,
            azimuth,
            elevation,
            bbox,
        ),
    ) in enumerate(
        cells,
        start=1,
    ):
        print(
            (
                f"[{index}/"
                f"{len(cells)}] "
                f"{name}"
            )
        )

        clear_cell(
            sheet_pixels,
            sheet_width,
            bbox,
        )

        render_path = render_view(
            camera=camera,
            target=target,
            model_size=model_size,
            name=name,
            azimuth=azimuth,
            elevation=elevation,
            bbox=bbox,
            ortho_scale=ortho_scale,
            output_dir=stills_dir,
        )

        composite_view(
            sheet_pixels,
            sheet_width,
            bbox,
            render_path,
        )

    # -----------------------------------------------------
    # Final Projection Tool
    # -----------------------------------------------------

    save_sheet(
        sheet_pixels,
        sheet_width,
        sheet_height,
        output_path,
    )

    if not output_path.exists():
        raise RuntimeError(
            (
                "Projection sheet was "
                "not generated: "
                f"{output_path}"
            )
        )

    if not args.keep_stills:
        shutil.rmtree(
            stills_dir
        )

    print(
        (
            "Projection sheet generated: "
            f"{output_path}"
        )
    )
