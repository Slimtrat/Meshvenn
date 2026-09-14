from pathlib import Path

# =========================================================
# Configuration
# =========================================================

DEFAULT_PACKAGE_ROOT = (
    Path("dist")
    / "blender_projection_tool"
)

OBJECT_NAME = (
    "MeshvennUVBakeSmokeObject"
)

MESH_NAME = (
    "MeshvennUVBakeSmokeMesh"
)

UV_LAYER_NAME = (
    "MeshvennUVBakeSmokeUV"
)

TEXTURE_SIZE = 8

FLOAT_TOLERANCE = 1e-5

RGBA8_TOLERANCE = 1e-6


REQUIRED_PACKAGE_FILES = (
    "__init__.py",

    "core/uv_bake.py",

    "implementations/__init__.py",
    "implementations/uv_bake.py",
)
