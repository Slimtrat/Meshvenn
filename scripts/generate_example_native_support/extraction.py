from __future__ import annotations

from .shared import BinaryMask, CELL_SPECS, ExtractedView, Path, RunLogger, array, bpy, hashlib, pixel_bbox
from .image_components import _apply_component_alpha, _copy_cell_pixels, _foreground_from_rgba, _largest_component, _mask_from_component

def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()

def _save_extracted_png(
    rgba: array,
    width: int,
    height: int,
    output_path: Path,
) -> None:
    image = bpy.data.images.new(
        name=(
            "BPT_"
            + output_path.stem
        ),
        width=width,
        height=height,
        alpha=True,
    )

    try:
        image.pixels.foreach_set(
            rgba
        )

        image.filepath_raw = str(
            output_path.resolve()
        )

        image.file_format = (
            "PNG"
        )

        image.save()

    finally:
        bpy.data.images.remove(
            image
        )

def extract_cell(
    sheet_pixels: array,
    sheet_width: int,
    output_path: Path,
    *,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    white_threshold: float,
    alpha_threshold: float,
) -> tuple[
    bool,
    BinaryMask,
]:
    (
        rgba,
        width,
        height,
    ) = _copy_cell_pixels(
        sheet_pixels,
        sheet_width,
        bbox,
    )

    foreground = (
        _foreground_from_rgba(
            rgba,
            width,
            height,
            white_threshold=(
                white_threshold
            ),
        )
    )

    component = (
        _largest_component(
            foreground,
            width,
            height,
        )
    )

    minimum_component = max(
        64,
        int(
            width
            * height
            * 0.005
        ),
    )

    valid = (
        len(component)
        >= minimum_component
    )

    keep = (
        _apply_component_alpha(
            rgba,
            width,
            height,
            component,
            valid=valid,
        )
    )

    mask = (
        _mask_from_component(
            rgba,
            keep,
            width,
            height,
            alpha_threshold=(
                alpha_threshold
            ),
        )
    )

    _save_extracted_png(
        rgba,
        width,
        height,
        output_path,
    )

    return (
        valid,
        mask,
    )

def extract_sheet(
    sheet_path: Path,
    output_dir: Path,
    *,
    white_threshold: float,
    alpha_threshold: float,
    logger: RunLogger,
) -> tuple[
    list[ExtractedView],
    dict,
]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    sheet = bpy.data.images.load(
        str(
            sheet_path.resolve()
        ),
        check_existing=False,
    )

    sheet.update()

    width = int(
        sheet.size[0]
    )

    height = int(
        sheet.size[1]
    )

    if (
        width <= 0
        or height <= 0
    ):
        bpy.data.images.remove(
            sheet
        )

        raise ValueError(
            (
                f"Invalid sheet size: "
                f"{width}x{height}"
            )
        )

    # Read Blender RNA pixels once.
    #
    # Direct repeated access through
    # image.pixels[index] is significantly
    # slower than foreach_get().

    sheet_pixels = array(
        "f",
        [0.0],
    ) * (
        width
        * height
        * 4
    )

    sheet.pixels.foreach_get(
        sheet_pixels
    )

    views: list[
        ExtractedView
    ] = []

    try:
        for (
            index,
            (
                name,
                column,
                row,
                azimuth,
                elevation,
            ),
        ) in enumerate(
            CELL_SPECS,
            start=1,
        ):
            logger.progress(
                index,
                len(
                    CELL_SPECS
                ),
                f"extract {name}",
            )

            bbox = pixel_bbox(
                width,
                height,
                column,
                row,
            )

            output_path = (
                output_dir
                / f"{name}.png"
            )

            (
                valid,
                mask,
            ) = extract_cell(
                sheet_pixels,
                width,
                output_path,
                bbox=bbox,
                white_threshold=(
                    white_threshold
                ),
                alpha_threshold=(
                    alpha_threshold
                ),
            )

            views.append(
                ExtractedView(
                    name=name,
                    path=output_path,
                    azimuth_degrees=(
                        azimuth
                    ),
                    elevation_degrees=(
                        elevation
                    ),
                    bbox=bbox,
                    sha256=sha256_file(
                        output_path
                    ),
                    valid=valid,
                    mask=mask,
                )
            )

    finally:
        bpy.data.images.remove(
            sheet
        )

    manifest = {
        "engine": "native-cpp",
        "source": str(
            sheet_path
        ),
        "source_sha256": (
            sha256_file(
                sheet_path
            )
        ),
        "sheet_width": width,
        "sheet_height": height,
        "cuts": [
            {
                "view": view.name,
                "azimuth": (
                    view.azimuth_degrees
                ),
                "elevation": (
                    view.elevation_degrees
                ),
                "bbox": list(
                    view.bbox
                ),
                "output": (
                    view.path.name
                ),
                "sha256": (
                    view.sha256
                ),
                "valid": (
                    view.valid
                ),
                "mask_pixels": (
                    view.mask.occupied_count
                ),
            }
            for view
            in views
        ],
    }

    return (
        views,
        manifest,
    )
