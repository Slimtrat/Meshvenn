from __future__ import annotations

from .shared import BenchmarkVariant, NativeScanner, PROJECTED_IMPLEMENTATION_ID, Path, RunLogger, UV_IMPLEMENTATION_ID, argparse, build_projection_source, extract_sheet, material_views_for_snapshot, prepare_material_views, prepare_projections
from .artifacts import write_json
from .geometry import validate_geometry_parity
from .render import compare_with_baseline, render_variant
from .variant import generate_variant

def benchmark_profile(
    runtime,
    *,
    sheet_name: str,
    profile: str,
    snapshot,
    source,
    sheet_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> tuple[
    BenchmarkVariant,
    list[
        BenchmarkVariant
    ],
]:
    profile_root = (
        sheet_root
        / profile
    )

    variants: list[
        BenchmarkVariant
    ] = []

    # -----------------------------------------------------
    # Projected Color baseline
    # -----------------------------------------------------

    baseline_root = (
        profile_root
        / PROJECTED_IMPLEMENTATION_ID
    )

    baseline = (
        generate_variant(
            runtime,

            sheet_name=(
                sheet_name
            ),

            profile=(
                profile
            ),

            implementation_id=(
                PROJECTED_IMPLEMENTATION_ID
            ),

            # Irrelevant to projected color, but required by
            # the shared settings adapter.
            texture_size=(
                args.texture_sizes[
                    0
                ]
            ),

            snapshot=(
                snapshot
            ),

            source=(
                source
            ),

            variant_root=(
                baseline_root
            ),

            args=(
                args
            ),

            logger=(
                logger
            ),
        )
    )

    render_variant(
        baseline,
        args=args,
    )

    variants.append(
        baseline
    )

    # -----------------------------------------------------
    # UV Bake sizes
    # -----------------------------------------------------

    for texture_size in (
        args.texture_sizes
    ):
        uv_root = (
            profile_root
            / UV_IMPLEMENTATION_ID
            / str(
                texture_size
            )
        )

        variant = (
            generate_variant(
                runtime,

                sheet_name=(
                    sheet_name
                ),

                profile=(
                    profile
                ),

                implementation_id=(
                    UV_IMPLEMENTATION_ID
                ),

                texture_size=(
                    texture_size
                ),

                snapshot=(
                    snapshot
                ),

                source=(
                    source
                ),

                variant_root=(
                    uv_root
                ),

                args=(
                    args
                ),

                logger=(
                    logger
                ),
            )
        )

        render_variant(
            variant,
            args=args,
        )

        compare_with_baseline(
            baseline,
            variant,
        )

        variants.append(
            variant
        )

    validate_geometry_parity(
        variants
    )

    return (
        baseline,
        variants[
            1:
        ],
    )

def benchmark_sheet(
    runtime,
    *,
    sheet_path: Path,
    output_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> tuple[
    list[
        BenchmarkVariant
    ],
    dict[
        tuple[
            str,
            str,
        ],
        Path,
    ],
]:
    sheet_name = (
        sheet_path.stem
    )

    sheet_root = (
        output_root
        / sheet_name
    )

    source_root = (
        sheet_root
        / "source"
    )

    with logger.section(
        f"benchmark {sheet_name}"
    ):
        (
            extracted_views,
            source_manifest,
        ) = (
            extract_sheet(
                sheet_path,

                source_root,

                white_threshold=(
                    args
                    .sheet_white_threshold
                ),

                alpha_threshold=(
                    args.threshold
                ),

                logger=(
                    logger.child()
                ),
            )
        )

        projections = (
            prepare_projections(
                extracted_views,
                logger=(
                    logger.child()
                ),
            )
        )

        material_views = (
            prepare_material_views(
                extracted_views,
                logger=(
                    logger.child()
                ),
            )
        )

        scanner = (
            NativeScanner()
        )

        scan_result = (
            scanner.scan_levels(
                projections,

                resolution=(
                    args.resolution
                ),

                levels=(
                    args.profiles
                ),

                symmetry_x=(
                    args.symmetry_x
                ),

                thread_count=(
                    args.thread_count
                ),

                build_meshes=True,

                voxel_size=(
                    args.voxel_size
                ),

                center_xy=True,

                mesh_mode=(
                    args.mesh_mode
                ),
            )
        )

        write_json(
            (
                sheet_root
                / "source.json"
            ),
            {
                "sheet": (
                    sheet_name
                ),

                "source": str(
                    sheet_path
                ),

                "manifest": (
                    source_manifest
                ),

                "available_views": list(
                    scan_result
                    .available_views
                ),

                "profiles": list(
                    scan_result
                    .requested_levels
                ),
            },
        )

        all_variants: list[
            BenchmarkVariant
        ] = []

        matrix_cells: dict[
            tuple[
                str,
                str,
            ],
            Path,
        ] = {}

        for profile in (
            args.profiles
        ):
            snapshot = (
                scan_result
                .snapshots
                .get(
                    profile
                )
            )

            if snapshot is None:
                raise RuntimeError(
                    (
                        "Native scan did not "
                        f"produce {profile}."
                    )
                )

            if snapshot.mesh is None:
                raise RuntimeError(
                    (
                        f"{profile} produced "
                        "no native mesh."
                    )
                )

            active_views = (
                material_views_for_snapshot(
                    material_views,

                    list(
                        snapshot
                        .applied_views
                    ),
                )
            )

            if not active_views:
                raise RuntimeError(
                    (
                        f"{profile} has no "
                        "material views."
                    )
                )

            source = (
                build_projection_source(
                    runtime,

                    extracted_views=(
                        extracted_views
                    ),

                    projections=(
                        projections
                    ),

                    material_views=(
                        material_views
                    ),

                    applied_views=(
                        snapshot
                        .applied_views
                    ),

                    alpha_threshold=(
                        args.threshold
                    ),
                )
            )

            (
                baseline,
                uv_variants,
            ) = (
                benchmark_profile(
                    runtime,

                    sheet_name=(
                        sheet_name
                    ),

                    profile=(
                        profile
                    ),

                    snapshot=(
                        snapshot
                    ),

                    source=(
                        source
                    ),

                    sheet_root=(
                        sheet_root
                    ),

                    args=(
                        args
                    ),

                    logger=(
                        logger.child()
                    ),
                )
            )

            all_variants.append(
                baseline
            )

            all_variants.extend(
                uv_variants
            )

            matrix_cells[
                (
                    profile,
                    "projected",
                )
            ] = (
                baseline
                .contact_sheet_path
            )

            for variant in (
                uv_variants
            ):
                matrix_cells[
                    (
                        profile,
                        f"uv-{variant.texture_size}",
                    )
                ] = (
                    variant
                    .contact_sheet_path
                )

        return (
            all_variants,
            matrix_cells,
        )
