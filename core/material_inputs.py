"""Opt-in, calibrated appearance inputs; never a replacement geometry source."""

from __future__ import annotations

from dataclasses import dataclass
import re
import math
from array import array
from typing import TYPE_CHECKING

from .geometry_contracts.projection import GeometryProjectionSpace
from .image_mask import BinaryMask
from .projection_math import ProjectionTransform, compile_projection, direction_to_camera
from .projection_alignment import ProjectionAlignment
if TYPE_CHECKING:
    from .projected_material.models import ProjectedMaterialView


@dataclass(frozen=True)
class MaterialProjectionInput:
    """Color-only views in an explicitly certified reconstruction frame.

    ``views`` contain image buffers, masks and camera transforms, not a source
    mesh, skeleton or depth. Geometry keeps its own INPUT unchanged. The caller
    must certify this frame and match every camera to the geometry's calibrated
    views; invalid opt-in inputs fail instead of falling back to neutral views.
    """

    views: tuple[ProjectedMaterialView, ...]
    projection_space: GeometryProjectionSpace
    source_sha256: str
    render_mode: str
    version: int = 1

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1:
            raise ValueError("Unsupported material projection input version.")
        if not isinstance(self.projection_space, GeometryProjectionSpace):
            raise TypeError("Appearance requires an explicit GeometryProjectionSpace.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("Appearance source_sha256 must be a lowercase SHA-256.")
        if self.render_mode not in {"base-color-emission", "source-color-image"}:
            raise ValueError("Appearance must declare its color provenance.")
        object.__setattr__(self, "views", tuple(self.views))
        # Preserve existing Blender-facing APIs. Only construction of an
        # appearance input needs their real types, not import of this contract.
        from .projected_material.models import ProjectedMaterialView
        from .projected_material.image_buffer import ImageBuffer
        for view in self.views:
            if type(view) is not ProjectedMaterialView:
                raise TypeError("Appearance views must be image-only ProjectedMaterialView values.")
            image = view.image
            if (type(image) is not ImageBuffer or type(image.width) is not int or type(image.height) is not int
                    or image.width <= 0 or image.height <= 0 or type(image.pixels) is not array
                    or image.pixels.typecode != "f" or len(image.pixels) != image.width * image.height * 4):
                raise TypeError("Appearance requires valid float RGBA image buffers.")
            if any(not math.isfinite(value) or not 0 <= value <= 1 for value in image.pixels):
                raise ValueError("Appearance RGBA buffers must be finite in [0, 1].")
            if (type(view.mask) is not BinaryMask or type(view.mask.width) is not int or type(view.mask.height) is not int
                    or type(view.mask.values) is not bytes or len(view.mask.values) != image.width * image.height
                    or (view.mask.width, view.mask.height) != (image.width, image.height)):
                raise TypeError("Appearance requires a calibrated image-sized alpha mask.")
            if any(value not in (0, 1) for value in view.mask.values):
                raise ValueError("Appearance alpha masks must be binary.")
            if type(view.transform) is not ProjectionTransform or type(view.alignment) is not ProjectionAlignment:
                raise TypeError("Appearance requires explicit projection transform and alignment.")
            transform = view.transform
            angles = {"azimuth_degrees": transform.azimuth_degrees, "elevation_degrees": transform.elevation_degrees}
            if (not all(math.isfinite(value) for value in angles.values()) or
                    transform != compile_projection(**angles, flip_x=transform.flip_x) or
                    view.camera_direction != direction_to_camera(**angles)):
                raise ValueError("Appearance camera transform is not certified.")
            if not math.isfinite(view.weight) or view.weight <= 0:
                raise ValueError("Appearance weights must be finite and positive.")
        names = [view.name for view in self.views]
        if not names or not all(type(name) is str and name.strip() for name in names) or len(set(names)) != len(names):
            raise ValueError("Appearance needs nonempty, uniquely named views.")

    def validate_for(self, geometry):
        # Buffer arrays are mutable in the existing public image API: check
        # them again at the MATERIAL boundary, not only when input is authored.
        self.__post_init__()
        if self.projection_space != geometry.projection_space:
            raise ValueError("Appearance projection frame differs from GEOMETRY.")
        reference = {view.name: view for view in geometry.source.material_views}
        if set(reference) != {view.name for view in self.views}:
            raise ValueError("Appearance cameras differ from GEOMETRY input views.")
        for view in self.views:
            original = reference[view.name]
            if (view.transform != original.transform or
                    view.alignment != original.alignment or
                    view.camera_direction != original.camera_direction or
                    (view.image.width, view.image.height) !=
                    (original.image.width, original.image.height)):
                raise ValueError(f"Appearance camera '{view.name}' is not calibrated to GEOMETRY.")
        return self.views

    def provenance(self):
        return {"version": self.version, "material_input_mode": "source-color-projection",
                "source_sha256": self.source_sha256, "render_mode": self.render_mode,
                "view_names": [view.name for view in self.views],
                "projection_convention": self.projection_space.convention.value}
