from __future__ import annotations

from .config import DEFAULT_NORMALIZE_HEIGHT
from .resolution import _config_from_settings


def _draw_optional_property(layout, settings, property_name: str, label: str) -> bool:
    if not hasattr(settings, property_name):
        return False
    layout.prop(settings, property_name, text=label)
    return True


def draw_sdf_settings(layout, context) -> None:
    settings = getattr(
        context.scene,
        "bpt_settings",
        None,
    )

    if settings is None:
        return

    backend_box = (
        layout.box()
    )

    backend_box.label(
        text=(
            "SDF V1 — Python Reference"
        ),
        icon="EXPERIMENTAL",
    )

    backend_box.label(
        text=(
            "Continuous sub-voxel "
            "Surface Nets"
        ),
    )

    geometry_box = (
        layout.box()
    )

    geometry_box.label(
        text="Field",
        icon="MOD_VOLUME",
    )

    if not _draw_optional_property(
        geometry_box,
        settings,
        "sdf_resolution",
        "Resolution",
    ):
        _draw_optional_property(
            geometry_box,
            settings,
            "resolution",
            "Resolution",
        )

    if not _draw_optional_property(
        geometry_box,
        settings,
        "sdf_symmetry_x",
        "Symmetry X",
    ):
        _draw_optional_property(
            geometry_box,
            settings,
            "symmetry_x",
            "Symmetry X",
        )

    _draw_optional_property(
        geometry_box,
        settings,
        "sdf_smoothness",
        "Constraint Smoothness",
    )

    _draw_optional_property(
        geometry_box,
        settings,
        "sdf_surface_offset",
        "Surface Offset",
    )

    _draw_optional_property(
        geometry_box,
        settings,
        "sdf_iso_level",
        "Iso Level",
    )

    output_box = (
        layout.box()
    )

    output_box.label(
        text="Output",
        icon="MESH_DATA",
    )

    _draw_optional_property(
        output_box,
        settings,
        "normalize_height",
        "Normalize Height",
    )

    if bool(
        getattr(
            settings,
            "normalize_height",
            DEFAULT_NORMALIZE_HEIGHT,
        )
    ):
        _draw_optional_property(
            output_box,
            settings,
            "target_height",
            "Target Height",
        )

    try:
        config = (
            _config_from_settings(
                settings
            )
        )

        backend_box.label(
            text=(
                f"{config.sample_count:,} "
                "SDF samples"
            ),
            icon="INFO",
        )

        backend_box.label(
            text=(
                f"Dense field ≈ "
                f"{config.estimated_field_mib:.1f} MiB"
            ),
        )

    except Exception:
        pass
