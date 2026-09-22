# =========================================================
# Stable implementation defaults
# =========================================================

DEFAULT_INPUT_IMPLEMENTATION_ID = (
    "projection-images"
)

DEFAULT_GEOMETRY_IMPLEMENTATION_ID = (
    "native-visual-hull"
)

DEFAULT_MATERIAL_IMPLEMENTATION_ID = (
    "projected-color-v1.2"
)

DEFAULT_RIG_IMPLEMENTATION_ID = "canonical-biped-v1"

DEFAULT_EXPORT_IMPLEMENTATION_ID = ""


# =========================================================
# SDF Reconstruction V1 defaults
#
# These intentionally mirror:
#
#     implementations/sdf_reconstruction/config.py
#
# The implementation remains authoritative for runtime
# validation.
#
# The current backend is the pure-Python reference backend.
# Its dense-field safety limit is ~160³, so the Blender UI
# deliberately caps the selectable reference resolution at
# 160 for now.
#
# When native SDF acceleration lands this limit can be
# raised independently from the public implementation id.
# =========================================================

DEFAULT_SDF_RESOLUTION = 96

MINIMUM_SDF_RESOLUTION = 16

MAXIMUM_SDF_REFERENCE_RESOLUTION = 160


DEFAULT_SDF_SYMMETRY_X = False

DEFAULT_SDF_SMOOTHNESS = 0.0

DEFAULT_SDF_SURFACE_OFFSET = 0.0

DEFAULT_SDF_ISO_LEVEL = 0.0

DEFAULT_SDF_GRADIENT_STEP_SCALE = 0.5


# =========================================================
# UV Bake defaults
#
# These values deliberately mirror:
#
#     implementations/uv_bake.py
#
# Keep the implementation as the authority for runtime
# validation. These Blender properties only expose a safe
# persistent UI surface.
# =========================================================

DEFAULT_UV_BAKE_TEXTURE_SIZE = "512"

DEFAULT_UV_BAKE_PADDING_PIXELS = 8

DEFAULT_UV_BAKE_SAMPLES_PER_AXIS = "1"

DEFAULT_UV_BAKE_UV_LAYER_NAME = (
    "MeshvennUV"
)

DEFAULT_UV_BAKE_ISLAND_MARGIN = 0.02

DEFAULT_UV_BAKE_ANGLE_LIMIT_DEGREES = 66.0

DEFAULT_UV_BAKE_REUSE_EXISTING_UV = False


UV_BAKE_TEXTURE_SIZE_ITEMS = (
    (
        "512",
        "512 px",
        (
            "Recommended default for interactive "
            "Meshvenn generation. Balanced UV density, "
            "bake time and exported asset size."
        ),
    ),
    (
        "1024",
        "1024 px",
        (
            "High-quality texture for final export or "
            "meshes requiring additional texture density. "
            "Significantly higher bake cost."
        ),
    ),
    (
        "2048",
        "2048 px",
        (
            "Higher-detail texture with significantly "
            "more bake samples."
        ),
    ),
    (
        "4096",
        "4096 px",
        (
            "Maximum V2 texture resolution. "
            "High memory and bake cost."
        ),
    ),
)


UV_BAKE_SAMPLE_ITEMS = (
    (
        "1",
        "1×1",
        (
            "One projected-color evaluation per "
            "covered texel."
        ),
    ),
    (
        "2",
        "2×2",
        (
            "Four projected-color evaluations per "
            "covered texel."
        ),
    ),
    (
        "3",
        "3×3",
        (
            "Nine projected-color evaluations per "
            "covered texel."
        ),
    ),
    (
        "4",
        "4×4",
        (
            "Sixteen projected-color evaluations per "
            "covered texel. Expensive."
        ),
    ),
)


# =========================================================
# Projection view
# =========================================================
