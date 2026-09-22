from __future__ import annotations

from .shared import BenchmarkVariant

def geometry_signature(
    variant: BenchmarkVariant,
) -> tuple[
    int,
    int,
    tuple[
        float,
        float,
        float,
    ],
]:
    geometry = (
        variant
        .info[
            "geometry"
        ]
    )

    return (
        int(
            geometry[
                "vertices"
            ]
        ),

        int(
            geometry[
                "faces"
            ]
        ),

        tuple(
            round(
                float(
                    value
                ),
                6,
            )
            for value
            in geometry[
                "dimensions"
            ]
        ),
    )

def validate_geometry_parity(
    variants: list[
        BenchmarkVariant
    ],
) -> None:
    if not variants:
        return

    reference = (
        geometry_signature(
            variants[
                0
            ]
        )
    )

    for variant in (
        variants[
            1:
        ]
    ):
        current = (
            geometry_signature(
                variant
            )
        )

        if current != reference:
            raise RuntimeError(
                (
                    "Geometry changed during "
                    "UV resolution benchmark.\n"
                    f"Reference: {reference}\n"
                    f"{variant.profile}/"
                    f"{variant.texture_size}: "
                    f"{current}"
                )
            )
