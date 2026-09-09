from __future__ import annotations

import argparse
import math
import shutil
import sys

from array import array
from pathlib import Path

import bpy

from mathutils import Vector


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.presheet_layout import (
    CELL_SPECS,
    pixel_bbox,
)

from scripts.render_turntable import (
    center_objects,
    clear_scene,
    create_camera,
    ensure_preview_material,
    import_glb,
    look_at,
    setup_lighting,
    setup_render,
)


CELL_INSET = 2


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1:
        ]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Render a generated GLB back into "
            "the original Projection Tool sheet."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Generated GLB.",
    )

    parser.add_argument(
        "--template",
        required=True,
        type=Path,
        help=(
            "Original Projection Tool sheet "
            "used as the visual template."
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Generated Projection Tool PNG.",
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--framing",
        type=float,
        default=1.15,
        help=(
            "Common orthographic framing "
            "multiplier for every view."
        ),
    )

    parser.add_argument(
        "--material-mode",
        choices=(
            "neutral",
            "original",
        ),
        default="neutral",
        help=(
            "neutral = geometry preview; "
            "original = preserve GLB materials."
        ),
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Sheet image
# ---------------------------------------------------------

def load_sheet(
    path: Path,
) -> tuple[
    array,
    int,
    int,
]:
    path = path.resolve()

    if not path.exists():
        raise FileNotFoundError(
            (
                "Missing Projection Tool sheet: "
                f"{path}"
            )
        )

    image = bpy.data.images.load(
        str(
            path
        ),
        check_existing=False,
    )

    try:
        image.update()

        width = int(
            image.size[0]
        )

        height = int(
            image.size[1]
        )

        if (
            width <= 0
            or height <= 0
        ):
            raise ValueError(
                (
                    "Invalid Projection Tool "
                    f"sheet size: {width}x{height}"
                )
            )

        pixels = array(
            "f",
            [0.0],
        ) * (
            width
            * height
            * 4
        )

        image.pixels.foreach_get(
            pixels
        )

        return (
            pixels,
            width,
            height,
        )

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Cell geometry
# ---------------------------------------------------------

def inset_bbox(
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    inset: int = CELL_INSET,
) -> tuple[
    int,
    int,
    int,
    int,
]:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    result = (
        x0 + inset,
        y0 + inset,
        x1 - inset,
        y1 - inset,
    )

    (
        ix0,
        iy0,
        ix1,
        iy1,
    ) = result

    if (
        ix1 <= ix0
        or iy1 <= iy0
    ):
        raise ValueError(
            (
                "Cell is too small after inset: "
                f"{bbox}"
            )
        )

    return result


def build_cells(
    sheet_width: int,
    sheet_height: int,
) -> list[
    tuple[
        str,
        float,
        float,
        tuple[
            int,
            int,
            int,
            int,
        ],
    ]
]:
    cells = []

    for (
        name,
        column,
        row,
        azimuth,
        elevation,
    ) in CELL_SPECS:
        bbox = pixel_bbox(
            sheet_width,
            sheet_height,
            column,
            row,
        )

        cells.append(
            (
                name,
                azimuth,
                elevation,
                inset_bbox(
                    bbox
                ),
            )
        )

    return cells


# ---------------------------------------------------------
# Cell cleanup
# ---------------------------------------------------------

def clear_cell(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
) -> None:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    for y in range(
        y0,
        y1,
    ):
        row_start = (
            (
                y
                * sheet_width
                + x0
            )
            * 4
        )

        for x in range(
            x0,
            x1,
        ):
            index = (
                row_start
                + (
                    x
                    - x0
                )
                * 4
            )

            sheet_pixels[
                index
            ] = 1.0

            sheet_pixels[
                index + 1
            ] = 1.0

            sheet_pixels[
                index + 2
            ] = 1.0

            sheet_pixels[
                index + 3
            ] = 1.0


# ---------------------------------------------------------
# Common framing
# ---------------------------------------------------------

def common_ortho_scale(
    model_size: Vector,
    cells: list[
        tuple[
            str,
            float,
            float,
            tuple[
                int,
                int,
                int,
                int,
            ],
        ]
    ],
    *,
    framing: float,
) -> float:
    if framing <= 0.0:
        raise ValueError(
            "framing must be greater than zero"
        )

    minimum_aspect = float(
        "inf"
    )

    for (
        _name,
        _azimuth,
        _elevation,
        bbox,
    ) in cells:
        (
            x0,
            y0,
            x1,
            y1,
        ) = bbox

        width = (
            x1
            - x0
        )

        height = (
            y1
            - y0
        )

        aspect = (
            width
            / height
        )

        minimum_aspect = min(
            minimum_aspect,
            aspect,
        )

    horizontal_max = math.hypot(
        model_size.x,
        model_size.y,
    )

    horizontal_views_scale = max(
        model_size.z,
        (
            horizontal_max
            / minimum_aspect
        ),
    )

    top_bottom_scale = max(
        model_size.x,
        model_size.y,
        (
            model_size.x
            / minimum_aspect
        ),
        (
            model_size.y
            / minimum_aspect
        ),
    )

    return (
        max(
            horizontal_views_scale,
            top_bottom_scale,
            0.01,
        )
        * framing
    )


# ---------------------------------------------------------
# Camera positioning
# ---------------------------------------------------------

def place_projection_camera(
    camera: bpy.types.Object,
    *,
    target: Vector,
    model_size: Vector,
    azimuth_degrees: float,
    elevation_degrees: float,
    ortho_scale: float,
) -> None:
    framing_size = max(
        model_size.x,
        model_size.y,
        model_size.z,
        0.01,
    )

    distance = (
        framing_size
        * 4.0
    )

    azimuth = math.radians(
        azimuth_degrees
    )

    elevation = math.radians(
        elevation_degrees
    )

    horizontal_distance = (
        math.cos(
            elevation
        )
        * distance
    )

    camera.location = (
        math.sin(
            azimuth
        )
        * horizontal_distance,
        -math.cos(
            azimuth
        )
        * horizontal_distance,
        math.sin(
            elevation
        )
        * distance,
    )

    look_at(
        camera,
        target,
    )

    camera.data.ortho_scale = (
        ortho_scale
    )


# ---------------------------------------------------------
# Render configuration
# ---------------------------------------------------------

def configure_projection_render(
    *,
    samples: int,
) -> None:
    # Reuse the existing visual-preview
    # renderer configuration.
    setup_render(
        size=256,
        samples=samples,
    )

    scene = (
        bpy.context.scene
    )

    # Projection-sheet renders need alpha because
    # they are composited into the original sheet.
    scene.render.film_transparent = (
        True
    )

    scene.render.image_settings.color_mode = (
        "RGBA"
    )


# ---------------------------------------------------------
# Render one view
# ---------------------------------------------------------

def render_view(
    *,
    camera: bpy.types.Object,
    target: Vector,
    model_size: Vector,
    name: str,
    azimuth: float,
    elevation: float,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    ortho_scale: float,
    output_dir: Path,
) -> Path:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    width = (
        x1
        - x0
    )

    height = (
        y1
        - y0
    )

    scene = (
        bpy.context.scene
    )

    scene.render.resolution_x = (
        width
    )

    scene.render.resolution_y = (
        height
    )

    scene.render.resolution_percentage = (
        100
    )

    place_projection_camera(
        camera,
        target=target,
        model_size=model_size,
        azimuth_degrees=azimuth,
        elevation_degrees=elevation,
        ortho_scale=ortho_scale,
    )

    output_path = (
        output_dir
        / f"{name}.png"
    )

    scene.render.filepath = str(
        output_path.resolve()
    )

    print(
        (
            "Rendering projection view "
            f"{name} "
            f"(azimuth={azimuth:.0f}, "
            f"elevation={elevation:.0f})"
        )
    )

    bpy.ops.render.render(
        write_still=True
    )

    if not output_path.exists():
        raise RuntimeError(
            (
                "Render did not produce: "
                f"{output_path}"
            )
        )

    return output_path


# ---------------------------------------------------------
# Composite
# ---------------------------------------------------------

def composite_view(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    render_path: Path,
) -> None:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    expected_width = (
        x1
        - x0
    )

    expected_height = (
        y1
        - y0
    )

    image = bpy.data.images.load(
        str(
            render_path.resolve()
        ),
        check_existing=False,
    )

    try:
        image.update()

        width = int(
            image.size[0]
        )

        height = int(
            image.size[1]
        )

        if (
            width != expected_width
            or height != expected_height
        ):
            raise ValueError(
                (
                    "Unexpected rendered cell size: "
                    f"{width}x{height}, "
                    "expected "
                    f"{expected_width}x"
                    f"{expected_height}"
                )
            )

        render_pixels = array(
            "f",
            [0.0],
        ) * (
            width
            * height
            * 4
        )

        image.pixels.foreach_get(
            render_pixels
        )

        premultiplied = (
            image.alpha_mode
            == "PREMUL"
        )

        for local_y in range(
            height
        ):
            for local_x in range(
                width
            ):
                source_index = (
                    (
                        local_y
                        * width
                        + local_x
                    )
                    * 4
                )

                destination_index = (
                    (
                        (
                            y0
                            + local_y
                        )
                        * sheet_width
                        + (
                            x0
                            + local_x
                        )
                    )
                    * 4
                )

                alpha = max(
                    0.0,
                    min(
                        1.0,
                        render_pixels[
                            source_index + 3
                        ],
                    ),
                )

                if premultiplied:
                    red = (
                        render_pixels[
                            source_index
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                    green = (
                        render_pixels[
                            source_index + 1
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                    blue = (
                        render_pixels[
                            source_index + 2
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                else:
                    red = (
                        render_pixels[
                            source_index
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                    green = (
                        render_pixels[
                            source_index + 1
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                    blue = (
                        render_pixels[
                            source_index + 2
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                sheet_pixels[
                    destination_index
                ] = red

                sheet_pixels[
                    destination_index + 1
                ] = green

                sheet_pixels[
                    destination_index + 2
                ] = blue

                sheet_pixels[
                    destination_index + 3
                ] = 1.0

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Save final sheet
# ---------------------------------------------------------

def save_sheet(
    pixels: array,
    width: int,
    height: int,
    output_path: Path,
) -> None:
    output_path = (
        output_path.resolve()
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = bpy.data.images.new(
        name="BPT_ProjectionSheet",
        width=width,
        height=height,
        alpha=True,
    )

    try:
        image.pixels.foreach_set(
            pixels
        )

        image.filepath_raw = str(
            output_path
        )

        image.file_format = (
            "PNG"
        )

        image.save()

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

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


if __name__ == "__main__":
    main()