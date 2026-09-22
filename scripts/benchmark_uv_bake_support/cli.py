from __future__ import annotations

from .shared import DEFAULT_ALPHA_THRESHOLD, DEFAULT_ANGLE_LIMIT_DEGREES, DEFAULT_EXAMPLE_DIR, DEFAULT_GEOMETRY_RESOLUTION, DEFAULT_GUTTER, DEFAULT_ISLAND_MARGIN, DEFAULT_MAX_SUBPIXEL_RATIO, DEFAULT_MESH_MODE, DEFAULT_OUTPUT_DIR, DEFAULT_PADDING_PIXELS, DEFAULT_PROFILES, DEFAULT_RENDER_SAMPLES, DEFAULT_RENDER_SIZE, DEFAULT_RENDER_VIEWS, DEFAULT_SAMPLES_PER_AXIS, DEFAULT_SHEET_WHITE_THRESHOLD, DEFAULT_TARGET_HEIGHT, DEFAULT_TEXTURE_SIZES, DEFAULT_UV_LAYER_NAME, DEFAULT_VOXEL_SIZE, Path, argparse, sys

def _script_arguments() -> list[str]:
    if "--" not in sys.argv:
        return []

    index = sys.argv.index(
        "--"
    )

    return sys.argv[
        index + 1:
    ]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Meshvenn UV Bake V2 at several "
            "texture resolutions using identical geometry."
        )
    )

    parser.add_argument(
        "--example-dir",
        type=Path,
        default=DEFAULT_EXAMPLE_DIR,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--sheets",
        nargs="+",
        default=[
            "sheet1",
        ],
    )

    parser.add_argument(
        "--profiles",
        nargs="+",
        default=list(
            DEFAULT_PROFILES
        ),
    )

    parser.add_argument(
        "--texture-sizes",
        nargs="+",
        type=int,
        default=list(
            DEFAULT_TEXTURE_SIZES
        ),
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=(
            DEFAULT_GEOMETRY_RESOLUTION
        ),
    )

    parser.add_argument(
        "--mesh-mode",
        choices=(
            "surface_nets",
            "blocks",
        ),
        default=DEFAULT_MESH_MODE,
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=(
            DEFAULT_ALPHA_THRESHOLD
        ),
    )

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=(
            DEFAULT_SHEET_WHITE_THRESHOLD
        ),
    )

    parser.add_argument(
        "--thread-count",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--symmetry-x",
        action="store_true",
    )

    parser.add_argument(
        "--voxel-size",
        type=float,
        default=(
            DEFAULT_VOXEL_SIZE
        ),
    )

    parser.add_argument(
        "--target-height",
        type=float,
        default=(
            DEFAULT_TARGET_HEIGHT
        ),
    )

    parser.add_argument(
        "--padding",
        type=int,
        default=(
            DEFAULT_PADDING_PIXELS
        ),
    )

    parser.add_argument(
        "--samples-per-axis",
        type=int,
        choices=(
            1,
            2,
            3,
            4,
        ),
        default=(
            DEFAULT_SAMPLES_PER_AXIS
        ),
    )

    parser.add_argument(
        "--uv-layer-name",
        default=(
            DEFAULT_UV_LAYER_NAME
        ),
    )

    parser.add_argument(
        "--island-margin",
        type=float,
        default=(
            DEFAULT_ISLAND_MARGIN
        ),
    )

    parser.add_argument(
        "--angle-limit",
        type=float,
        default=(
            DEFAULT_ANGLE_LIMIT_DEGREES
        ),
    )

    parser.add_argument(
        "--render-size",
        type=int,
        default=(
            DEFAULT_RENDER_SIZE
        ),
    )

    parser.add_argument(
        "--views",
        type=int,
        default=(
            DEFAULT_RENDER_VIEWS
        ),
    )

    parser.add_argument(
        "--render-samples",
        type=int,
        default=(
            DEFAULT_RENDER_SAMPLES
        ),
    )

    parser.add_argument(
        "--max-subpixel-ratio",
        type=float,
        default=(
            DEFAULT_MAX_SUBPIXEL_RATIO
        ),
        help=(
            "Technical target used when suggesting the "
            "smallest acceptable UV resolution."
        ),
    )

    parser.add_argument(
        "--gutter",
        type=int,
        default=(
            DEFAULT_GUTTER
        ),
    )

    parser.add_argument(
        "--save-blend",
        action="store_true",
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args(
        _script_arguments()
    )

def _unique_ordered(
    values,
) -> list:
    result = []

    for value in values:
        if value not in result:
            result.append(
                value
            )

    return result

def validate_args(
    args: argparse.Namespace,
) -> None:
    if not (
        8
        <= args.resolution
        <= 256
    ):
        raise ValueError(
            (
                "Geometry resolution must "
                "be between 8 and 256."
            )
        )

    args.profiles = (
        _unique_ordered(
            [
                str(profile)
                .strip()
                .upper()
                for profile
                in args.profiles
            ]
        )
    )

    for profile in args.profiles:
        if profile not in {
            "L2",
            "L4",
            "L8",
            "L10",
        }:
            raise ValueError(
                (
                    "Unsupported profile: "
                    f"{profile}"
                )
            )

    if not args.profiles:
        raise ValueError(
            (
                "At least one profile "
                "is required."
            )
        )

    args.texture_sizes = (
        sorted(
            set(
                args.texture_sizes
            )
        )
    )

    allowed_texture_sizes = {
        64,
        128,
        256,
        512,
        1024,
        2048,
        4096,
    }

    if not args.texture_sizes:
        raise ValueError(
            (
                "At least one texture "
                "size is required."
            )
        )

    for texture_size in (
        args.texture_sizes
    ):
        if (
            texture_size
            not in allowed_texture_sizes
        ):
            raise ValueError(
                (
                    "Unsupported texture size: "
                    f"{texture_size}"
                )
            )

    if not (
        0
        <= args.padding
        <= 128
    ):
        raise ValueError(
            (
                "Padding must be "
                "between 0 and 128."
            )
        )

    if not (
        4
        <= args.views
        <= 16
    ):
        raise ValueError(
            (
                "Views must be "
                "between 4 and 16."
            )
        )

    if args.render_size < 128:
        raise ValueError(
            (
                "Render size must "
                "be >= 128."
            )
        )

    if args.render_samples < 1:
        raise ValueError(
            (
                "Render samples must "
                "be >= 1."
            )
        )

    if not (
        0.0
        <= args.max_subpixel_ratio
        <= 1.0
    ):
        raise ValueError(
            (
                "max-subpixel-ratio must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        <= args.threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Alpha threshold must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        <= args.sheet_white_threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Sheet white threshold must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        <= args.island_margin
        <= 1.0
    ):
        raise ValueError(
            (
                "Island margin must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        < args.angle_limit
        <= 90.0
    ):
        raise ValueError(
            (
                "Angle limit must "
                "be inside ]0, 90]."
            )
        )

    if args.voxel_size <= 0.0:
        raise ValueError(
            (
                "Voxel size must "
                "be positive."
            )
        )

    if args.target_height <= 0.0:
        raise ValueError(
            (
                "Target height must "
                "be positive."
            )
        )
