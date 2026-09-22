from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]


# =========================================================
# Constants
# =========================================================

SUPPORTED_IMPLEMENTATIONS = (
    "projected-color-v1.2",
    "uv-bake-v2",
)

DEFAULT_EXAMPLE_DIR = (
    REPO_ROOT
    / "example"
    / "mascotte"
    / "test1"
)

DEFAULT_PROFILES = (
    "L2",
    "L4",
    "L8",
    "L10",
)

DEFAULT_RESOLUTION = 64

DEFAULT_TEXTURE_SIZE = 256

DEFAULT_PADDING_PIXELS = 4

DEFAULT_SAMPLES_PER_AXIS = 1

DEFAULT_MESH_MODE = (
    "surface_nets"
)

DEFAULT_TARGET_HEIGHT = 2.0

DEFAULT_ALPHA_THRESHOLD = 0.1

DEFAULT_SHEET_WHITE_THRESHOLD = 0.94

DEFAULT_VOXEL_SIZE = 1.0

DEFAULT_UV_LAYER_NAME = (
    "MeshvennCompareUV"
)

DEFAULT_ISLAND_MARGIN = 0.02

DEFAULT_ANGLE_LIMIT_DEGREES = 66.0


# =========================================================
# Runtime package
# =========================================================

@dataclass(frozen=True)
class PipelineRuntime:
    package_name: str

    contracts: ModuleType

    projection_images: ModuleType

    native_visual_hull: ModuleType

    projected_color: ModuleType

    uv_bake: ModuleType


def load_pipeline_runtime() -> PipelineRuntime:
    """
    Load the production pipeline modules through Meshvenn's
    real package namespace.

    Existing historical scripts import core/ directly because
    they predate the generic pipeline.

    implementations/ uses package-relative imports:

        ..core
        .native_visual_hull

    so this comparison runner loads those implementations
    through the repository package itself.

    No Blender add-on registration is required.
    """

    package_name = (
        REPO_ROOT.name
    )

    if not package_name.isidentifier():
        raise RuntimeError(
            (
                "Repository directory must be a valid "
                "Python package name to run material "
                "comparison. "
                f"Received: {package_name!r}"
            )
        )

    package_parent = str(
        REPO_ROOT.parent
    )

    if package_parent not in sys.path:
        sys.path.insert(
            0,
            package_parent,
        )

    # Import root package once so relative implementation
    # imports resolve exactly as they do in the Blender
    # extension.
    importlib.import_module(
        package_name
    )

    return PipelineRuntime(
        package_name=package_name,

        contracts=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "core.pipeline_contracts"
                )
            )
        ),

        projection_images=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.projection_images"
                )
            )
        ),

        native_visual_hull=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.native_visual_hull"
                )
            )
        ),

        projected_color=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.projected_color"
                )
            )
        ),

        uv_bake=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.uv_bake"
                )
            )
        ),
    )
