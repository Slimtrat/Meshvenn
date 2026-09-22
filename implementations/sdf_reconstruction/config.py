from __future__ import annotations

import math
from dataclasses import dataclass

from ...core.sdf import (
    DEFAULT_ISO_LEVEL,
    DEFAULT_REFERENCE_MAX_VOXELS,
    DEFAULT_SMOOTHNESS,
    DEFAULT_SURFACE_OFFSET,
    SDFBuildConfig,
)
from ...core.sdf_surface import DEFAULT_GRADIENT_STEP_SCALE, SDFSurfaceConfig

# =========================================================
# Constants
# =========================================================

IMPLEMENTATION_ID = (
    "sdf-reconstruction-v1"
)

IMPLEMENTATION_VERSION = (
    "1"
)


DEFAULT_RESOLUTION = 96

MINIMUM_RESOLUTION = 16

MAXIMUM_RESOLUTION = 256


DEFAULT_VOXEL_SIZE = 1.0

DEFAULT_CENTER_XY = True


DEFAULT_NORMALIZE_HEIGHT = True

DEFAULT_TARGET_HEIGHT = 2.0


DEFAULT_OBJECT_NAME = (
    "MeshvennSDF"
)

DEFAULT_MESH_NAME = (
    "MeshvennSDFMesh"
)


MINIMUM_PROJECTION_COUNT = 2


# =========================================================
# Configuration
# =========================================================

@dataclass(frozen=True)
class SDFReconstructionConfig:
    """
    Effective SDF Reconstruction V1 configuration.

    The first implementation deliberately uses the pure
    Python reference core.

    This gives us a correctness baseline before moving the
    expensive field construction / Surface Nets extraction
    to C++.

    Existing generic settings remain valid:

        resolution
        symmetry_x
        normalize_height
        target_height

    SDF-specific properties are read defensively when
    available:

        sdf_resolution
        sdf_symmetry_x
        sdf_voxel_size
        sdf_smoothness
        sdf_surface_offset
        sdf_iso_level
        sdf_gradient_step_scale

    This means the implementation can land before the UI
    properties without breaking older .blend files.
    """

    resolution: int = (
        DEFAULT_RESOLUTION
    )

    symmetry_x: bool = False

    voxel_size: float = (
        DEFAULT_VOXEL_SIZE
    )

    center_xy: bool = (
        DEFAULT_CENTER_XY
    )

    smoothness: float = (
        DEFAULT_SMOOTHNESS
    )

    surface_offset: float = (
        DEFAULT_SURFACE_OFFSET
    )

    iso_level: float = (
        DEFAULT_ISO_LEVEL
    )

    gradient_step_scale: float = (
        DEFAULT_GRADIENT_STEP_SCALE
    )

    normalize_height: bool = (
        DEFAULT_NORMALIZE_HEIGHT
    )

    target_height: float = (
        DEFAULT_TARGET_HEIGHT
    )

    max_reference_voxels: int = (
        DEFAULT_REFERENCE_MAX_VOXELS
    )

    def validate(
        self,
    ) -> None:
        if (
            not isinstance(
                self.resolution,
                int,
            )
            or isinstance(
                self.resolution,
                bool,
            )
            or self.resolution
            < MINIMUM_RESOLUTION
            or self.resolution
            > MAXIMUM_RESOLUTION
        ):
            raise ValueError(
                (
                    "SDF resolution must be "
                    f"between {MINIMUM_RESOLUTION} "
                    f"and {MAXIMUM_RESOLUTION}."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.voxel_size
                )
            )
            or self.voxel_size <= 0.0
        ):
            raise ValueError(
                (
                    "SDF voxel size must be "
                    "finite and greater than zero."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.smoothness
                )
            )
            or self.smoothness < 0.0
        ):
            raise ValueError(
                (
                    "SDF smoothness must be "
                    "finite and >= 0."
                )
            )

        if not math.isfinite(
            float(
                self.surface_offset
            )
        ):
            raise ValueError(
                (
                    "SDF surface offset "
                    "must be finite."
                )
            )

        if not math.isfinite(
            float(
                self.iso_level
            )
        ):
            raise ValueError(
                (
                    "SDF iso level "
                    "must be finite."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.gradient_step_scale
                )
            )
            or self.gradient_step_scale
            <= 0.0
        ):
            raise ValueError(
                (
                    "SDF gradient step "
                    "must be finite and "
                    "greater than zero."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.target_height
                )
            )
            or self.target_height <= 0.0
        ):
            raise ValueError(
                (
                    "Target height must be "
                    "finite and greater than zero."
                )
            )

        # -------------------------------------------------
        # Also validates the pure-Python reference memory /
        # sample-count guard.
        # -------------------------------------------------

        self.to_build_config().validate()

        self.to_surface_config().validate()

    @property
    def sample_count(
        self,
    ) -> int:
        return (
            self.resolution
            * self.resolution
            * self.resolution
        )

    @property
    def estimated_field_bytes(
        self,
    ) -> int:
        # Dense float32 SDF field only.
        return (
            self.sample_count
            * 4
        )

    @property
    def estimated_field_mib(
        self,
    ) -> float:
        return (
            float(
                self.estimated_field_bytes
            )
            / (
                1024.0
                * 1024.0
            )
        )

    def to_build_config(
        self,
    ) -> SDFBuildConfig:
        return SDFBuildConfig(
            width=(
                self.resolution
            ),

            depth=(
                self.resolution
            ),

            height=(
                self.resolution
            ),

            symmetry_x=(
                self.symmetry_x
            ),

            smoothness=(
                self.smoothness
            ),

            surface_offset=(
                self.surface_offset
            ),

            iso_level=(
                self.iso_level
            ),

            max_voxels=(
                self.max_reference_voxels
            ),
        )

    def to_surface_config(
        self,
    ) -> SDFSurfaceConfig:
        return SDFSurfaceConfig(
            iso_level=(
                self.iso_level
            ),

            gradient_step_scale=(
                self.gradient_step_scale
            ),

            generate_normals=True,
        )
