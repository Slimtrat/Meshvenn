from __future__ import annotations

from .shared import Any, Path

def material_diagnostics(
    result,
) -> dict[str, Any]:
    payload = (
        result.payload
    )

    diagnostics: dict[
        str,
        Any,
    ] = {}

    bake_result = getattr(
        payload,
        "bake_result",
        None,
    )

    if bake_result is not None:
        stats = (
            bake_result.stats
        )

        diagnostics[
            "uv_bake"
        ] = {
            "texture_width": (
                bake_result
                .texture
                .width
            ),

            "texture_height": (
                bake_result
                .texture
                .height
            ),

            "triangle_count": (
                stats.triangle_count
            ),

            "rasterized_triangles": (
                stats
                .rasterized_triangles
            ),

            "degenerate_triangles": (
                stats
                .degenerate_triangles
            ),

            "covered_pixels": (
                stats.covered_pixels
            ),

            "padded_pixels": (
                stats.padded_pixels
            ),

            "overlap_pixels": (
                stats.overlap_pixels
            ),

            "surface_samples": (
                stats.surface_samples
            ),

            "fallback_samples": (
                stats.fallback_samples
            ),

            "selected_source_samples": (
                stats
                .selected_source_samples
            ),

            "coverage_ratio": (
                stats.coverage_ratio
            ),

            "filled_pixels": (
                stats.filled_pixels
            ),

            "filled_ratio": (
                float(
                    stats.filled_pixels
                )
                / float(
                    stats.texture_pixels
                )
                if stats.texture_pixels
                else 0.0
            ),
        }

    projected_stats = getattr(
        payload,
        "stats",
        None,
    )

    if projected_stats is not None:
        diagnostics[
            "projected_color"
        ] = {
            "vertex_count": (
                projected_stats
                .vertex_count
            ),

            "view_count": (
                projected_stats
                .view_count
            ),

            "projected_vertices": (
                projected_stats
                .projected_vertices
            ),

            "fallback_vertices": (
                projected_stats
                .fallback_vertices
            ),

            "visible_samples": (
                projected_stats
                .visible_samples
            ),

            "occluded_samples": (
                projected_stats
                .occluded_samples
            ),

            "selected_samples": (
                projected_stats
                .selected_samples
            ),
        }

    return diagnostics

def save_baked_texture(
    payload,
    output_path: Path,
) -> Path | None:
    image = getattr(
        payload,
        "image",
        None,
    )

    if image is None:
        return None

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image.filepath_raw = str(
        output_path.resolve()
    )

    image.file_format = (
        "PNG"
    )

    image.save()

    if not output_path.is_file():
        raise RuntimeError(
            (
                "Baked texture was "
                "not written: "
                f"{output_path}"
            )
        )

    return output_path
