from __future__ import annotations

from .shared import Any, UV_IMPLEMENTATION_ID

def recommend_resolution(
    rows: list[
        dict[str, Any]
    ],
    *,
    profiles: list[str],
    texture_sizes: list[int],
    max_subpixel_ratio: float,
) -> dict[str, Any]:
    """
    This is deliberately a technical candidate, not an
    aesthetic verdict.

    Select the smallest texture size for which every tested
    profile reaches the requested subpixel-triangle target.
    """

    uv_rows = [
        row
        for row
        in rows
        if (
            row[
                "implementation"
            ]
            == UV_IMPLEMENTATION_ID
        )
    ]

    for texture_size in (
        texture_sizes
    ):
        size_rows = {
            row[
                "profile"
            ]: row
            for row
            in uv_rows
            if (
                row[
                    "texture_size"
                ]
                == texture_size
            )
        }

        if any(
            profile
            not in size_rows
            for profile
            in profiles
        ):
            continue

        passes = True

        reasons = []

        for profile in profiles:
            row = (
                size_rows[
                    profile
                ]
            )

            subpixel = (
                row[
                    "subpixel_triangle_ratio"
                ]
            )

            coverage = (
                row[
                    "coverage_ratio"
                ]
            )

            if subpixel is None:
                passes = False

                reasons.append(
                    (
                        f"{profile}: missing "
                        "subpixel metric"
                    )
                )

            elif (
                float(
                    subpixel
                )
                > max_subpixel_ratio
            ):
                passes = False

                reasons.append(
                    (
                        f"{profile}: "
                        f"{float(subpixel) * 100.0:.2f}% "
                        "subpixel triangles"
                    )
                )

            if (
                coverage is None
                or float(
                    coverage
                )
                <= 0.0
            ):
                passes = False

                reasons.append(
                    (
                        f"{profile}: "
                        "invalid UV coverage"
                    )
                )

        if passes:
            return {
                "texture_size": (
                    texture_size
                ),

                "target_met": True,

                "max_subpixel_ratio": (
                    max_subpixel_ratio
                ),

                "reason": (
                    "Smallest tested texture size "
                    "meeting the subpixel target "
                    "for every tested profile."
                ),
            }

    return {
        "texture_size": (
            max(
                texture_sizes
            )
        ),

        "target_met": False,

        "max_subpixel_ratio": (
            max_subpixel_ratio
        ),

        "reason": (
            "No tested resolution met the subpixel "
            "target for every profile. The largest "
            "tested size is retained as the technical "
            "candidate."
        ),
    }
