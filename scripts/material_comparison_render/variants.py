from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .config import DIMENSION_TOLERANCE, Variant

# =========================================================
# JSON
# =========================================================

def read_json(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            (
                "Missing JSON file: "
                f"{path}"
            )
        )

    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise TypeError(
            (
                "Expected JSON object: "
                f"{path}"
            )
        )

    return value


def write_json(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# =========================================================
# Discovery
# =========================================================

def discover_sheets(
    comparison_root: Path,
    requested: list[str] | None,
) -> list[str]:
    if not comparison_root.is_dir():
        raise FileNotFoundError(
            (
                "Comparison directory "
                "does not exist: "
                f"{comparison_root}"
            )
        )

    available = sorted(
        path.name
        for path
        in comparison_root.iterdir()
        if (
            path.is_dir()
            and path.name.startswith(
                "sheet"
            )
        )
    )

    if not available:
        raise RuntimeError(
            (
                "No sheet directories found "
                f"in {comparison_root}"
            )
        )

    if not requested:
        return available

    normalized = {
        Path(value).stem
        for value
        in requested
        if str(value).strip()
    }

    selected = [
        name
        for name
        in available
        if name in normalized
    ]

    missing = sorted(
        normalized
        - set(
            selected
        )
    )

    if missing:
        raise ValueError(
            (
                "Unknown sheets: "
                + ", ".join(
                    missing
                )
            )
        )

    return selected


# =========================================================
# Variants
# =========================================================

def load_variant(
    comparison_root: Path,
    *,
    sheet: str,
    profile: str,
    implementation: str,
) -> Variant:
    root = (
        comparison_root
        / sheet
        / profile
        / implementation
    )

    model_path = (
        root
        / "model.glb"
    )

    manifest_path = (
        root
        / "variant.json"
    )

    if not model_path.is_file():
        raise FileNotFoundError(
            (
                "Missing comparison model: "
                f"{model_path}"
            )
        )

    metadata = (
        read_json(
            manifest_path
        )
    )

    render_root = (
        root
        / "render"
    )

    contact_sheet_path = (
        render_root
        / "contact_sheet.png"
    )

    return Variant(
        sheet=sheet,

        profile=profile,

        implementation=(
            implementation
        ),

        root=root,

        model_path=(
            model_path
        ),

        manifest_path=(
            manifest_path
        ),

        render_root=(
            render_root
        ),

        contact_sheet_path=(
            contact_sheet_path
        ),

        metadata=(
            metadata
        ),
    )


# =========================================================
# Geometry parity
# =========================================================

def _geometry_signature(
    variant: Variant,
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
        .metadata
        .get(
            "geometry"
        )
    )

    if not isinstance(
        geometry,
        dict,
    ):
        raise RuntimeError(
            (
                "Variant has no geometry "
                f"metadata: {variant.root}"
            )
        )

    vertices = int(
        geometry[
            "vertices"
        ]
    )

    faces = int(
        geometry[
            "faces"
        ]
    )

    raw_dimensions = (
        geometry[
            "dimensions"
        ]
    )

    if (
        not isinstance(
            raw_dimensions,
            list,
        )
        or len(
            raw_dimensions
        )
        != 3
    ):
        raise RuntimeError(
            (
                "Invalid dimensions in "
                f"{variant.manifest_path}"
            )
        )

    dimensions = (
        float(
            raw_dimensions[0]
        ),
        float(
            raw_dimensions[1]
        ),
        float(
            raw_dimensions[2]
        ),
    )

    return (
        vertices,
        faces,
        dimensions,
    )


def validate_geometry_parity(
    variants: list[
        Variant
    ],
) -> None:
    """
    MATERIAL comparison is only useful when every variant
    uses exactly the same geometry.

    Vertex/face counts must match exactly.

    Dimensions may differ only by tiny floating-point noise.
    """

    if len(
        variants
    ) <= 1:
        return

    reference = (
        variants[
            0
        ]
    )

    (
        reference_vertices,
        reference_faces,
        reference_dimensions,
    ) = (
        _geometry_signature(
            reference
        )
    )

    for variant in (
        variants[
            1:
        ]
    ):
        (
            vertices,
            faces,
            dimensions,
        ) = (
            _geometry_signature(
                variant
            )
        )

        if (
            vertices
            != reference_vertices
        ):
            raise RuntimeError(
                (
                    "Geometry parity failure "
                    f"for {variant.sheet}/"
                    f"{variant.profile}: "
                    f"{reference.implementation} has "
                    f"{reference_vertices} vertices, "
                    f"{variant.implementation} has "
                    f"{vertices}."
                )
            )

        if faces != reference_faces:
            raise RuntimeError(
                (
                    "Geometry parity failure "
                    f"for {variant.sheet}/"
                    f"{variant.profile}: "
                    f"{reference.implementation} has "
                    f"{reference_faces} faces, "
                    f"{variant.implementation} has "
                    f"{faces}."
                )
            )

        for axis in range(
            3
        ):
            if not math.isclose(
                dimensions[
                    axis
                ],
                reference_dimensions[
                    axis
                ],
                rel_tol=(
                    DIMENSION_TOLERANCE
                ),
                abs_tol=(
                    DIMENSION_TOLERANCE
                ),
            ):
                raise RuntimeError(
                    (
                        "Geometry dimensions differ "
                        f"for {variant.sheet}/"
                        f"{variant.profile} "
                        f"on axis {axis}."
                    )
                )
