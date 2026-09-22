from __future__ import annotations

from .shared import BenchmarkVariant, IMAGE_DIFF_THRESHOLD, Path, argparse, array, bpy, math, render_turntable, shutil, time

def render_variant(
    variant: BenchmarkVariant,
    *,
    args: argparse.Namespace,
) -> None:
    if (
        variant
        .render_root
        .exists()
    ):
        shutil.rmtree(
            variant
            .render_root
        )

    started_at = (
        time.perf_counter()
    )

    contact_path = (
        render_turntable(
            variant.model_path,

            variant.render_root,

            views=(
                args.views
            ),

            size=(
                args.render_size
            ),

            samples=(
                args.render_samples
            ),

            keep_stills=(
                args.keep_stills
            ),

            preserve_material=True,
        )
    )

    variant.render_seconds = (
        time.perf_counter()
        - started_at
    )

    variant.contact_sheet_path = (
        contact_path
    )

    if not contact_path.is_file():
        raise RuntimeError(
            (
                "Render did not produce "
                f"{contact_path}"
            )
        )

def load_image_pixels(
    path: Path,
) -> tuple[
    array,
    int,
    int,
]:
    image = (
        bpy.data.images.load(
            str(
                path.resolve()
            ),
            check_existing=False,
        )
    )

    try:
        image.update()

        width = int(
            image.size[
                0
            ]
        )

        height = int(
            image.size[
                1
            ]
        )

        pixels = (
            array(
                "f",
                [
                    0.0
                ],
            )
            * (
                width
                * height
                * 4
            )
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

def compare_render_images(
    reference_path: Path,
    candidate_path: Path,
) -> dict[str, float]:
    (
        reference,
        reference_width,
        reference_height,
    ) = (
        load_image_pixels(
            reference_path
        )
    )

    (
        candidate,
        candidate_width,
        candidate_height,
    ) = (
        load_image_pixels(
            candidate_path
        )
    )

    if (
        reference_width
        != candidate_width
        or reference_height
        != candidate_height
    ):
        raise RuntimeError(
            (
                "Cannot compare render "
                "images with different sizes."
            )
        )

    pixel_count = (
        reference_width
        * reference_height
    )

    channel_count = (
        pixel_count
        * 3
    )

    absolute_error = 0.0

    squared_error = 0.0

    changed_pixels = 0

    for pixel_index in range(
        pixel_count
    ):
        offset = (
            pixel_index
            * 4
        )

        pixel_changed = False

        for channel in range(
            3
        ):
            difference = abs(
                float(
                    reference[
                        offset
                        + channel
                    ]
                )
                - float(
                    candidate[
                        offset
                        + channel
                    ]
                )
            )

            absolute_error += (
                difference
            )

            squared_error += (
                difference
                * difference
            )

            if (
                difference
                > IMAGE_DIFF_THRESHOLD
            ):
                pixel_changed = True

        if pixel_changed:
            changed_pixels += 1

    mae = (
        absolute_error
        / float(
            channel_count
        )
    )

    mse = (
        squared_error
        / float(
            channel_count
        )
    )

    rmse = math.sqrt(
        mse
    )

    if mse <= 0.0:
        psnr = float(
            "inf"
        )

    else:
        psnr = (
            10.0
            * math.log10(
                1.0
                / mse
            )
        )

    return {
        "rgb_mae": (
            mae
        ),

        "rgb_rmse": (
            rmse
        ),

        "psnr": (
            psnr
        ),

        "changed_pixel_ratio": (
            float(
                changed_pixels
            )
            / float(
                pixel_count
            )
        ),
    }

def compare_with_baseline(
    baseline: BenchmarkVariant,
    candidate: BenchmarkVariant,
) -> None:
    metrics = (
        compare_render_images(
            baseline
            .contact_sheet_path,

            candidate
            .contact_sheet_path,
        )
    )

    candidate.rgb_mae_vs_baseline = (
        metrics[
            "rgb_mae"
        ]
    )

    candidate.rgb_rmse_vs_baseline = (
        metrics[
            "rgb_rmse"
        ]
    )

    candidate.psnr_vs_baseline = (
        metrics[
            "psnr"
        ]
    )

    candidate.changed_pixel_ratio_vs_baseline = (
        metrics[
            "changed_pixel_ratio"
        ]
    )
