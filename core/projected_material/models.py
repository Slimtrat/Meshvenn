from __future__ import annotations
from dataclasses import dataclass, field
import bpy
from ..image_mask import BinaryMask
from ..projection_alignment import ProjectionAlignment
from ..material_blend import MaterialColorCandidate
from ..projection_math import ProjectionTransform, compile_projection, direction_to_camera
from .image_buffer import ImageBuffer

@dataclass(frozen=True)
class ProjectedMaterialView:
    """
    One RGB projection participating in material selection.

    Geometry reconstruction and appearance remain separate:

        NativeProjection
            -> geometry

        ProjectedMaterialView
            -> appearance
    """
    name: str
    image: ImageBuffer
    transform: ProjectionTransform
    mask: BinaryMask | None
    camera_direction: tuple[float, float, float]
    weight: float = 1.0
    alignment: ProjectionAlignment = field(default_factory=ProjectionAlignment)

    @classmethod
    def from_blender_image(
        cls, *, name: str, image: bpy.types.Image,
        azimuth_degrees: float, elevation_degrees: float,
        flip_x: bool = False, weight: float = 1.0,
        mask: BinaryMask | None = None,
        alignment: ProjectionAlignment | None = None,
    ) -> 'ProjectedMaterialView':
        return cls.from_image_buffer(
            name=name,
            image_buffer=ImageBuffer.from_blender_image(image),
            azimuth_degrees=azimuth_degrees,
            elevation_degrees=elevation_degrees,
            flip_x=flip_x,
            weight=weight,
            mask=mask,
            alignment=alignment,
        )

    @classmethod
    def from_image_buffer(
        cls, *, name: str, image_buffer: ImageBuffer,
        azimuth_degrees: float, elevation_degrees: float,
        flip_x: bool = False, weight: float = 1.0,
        mask: BinaryMask | None = None,
        alignment: ProjectionAlignment | None = None,
    ) -> 'ProjectedMaterialView':
        if mask is not None:
            if mask.width != image_buffer.width or mask.height != image_buffer.height:
                raise ValueError(f'Projection "{name}" image/mask dimensions differ: image={image_buffer.width}x{image_buffer.height}, mask={mask.width}x{mask.height}.')
        normalized_weight = max(0.0, float(weight))
        return cls(
            name=str(name),
            image=image_buffer,
            transform=compile_projection(
                azimuth_degrees=azimuth_degrees,
                elevation_degrees=elevation_degrees,
                flip_x=flip_x,
            ),
            mask=mask,
            camera_direction=direction_to_camera(
                azimuth_degrees=azimuth_degrees,
                elevation_degrees=elevation_degrees,
            ),
            weight=normalized_weight,
            alignment=alignment or ProjectionAlignment(),
        )

@dataclass(frozen=True)
class MaterialProjectionStats:
    vertex_count: int
    loop_count: int
    view_count: int
    projected_vertices: int
    fallback_vertices: int
    rejected_samples: int
    accepted_samples: int
    candidate_samples: int
    source_rejected_samples: int
    visible_samples: int
    occluded_samples: int
    front_facing_samples: int
    backface_samples: int
    grazing_rejected_samples: int
    relative_rejected_samples: int
    top_k_rejected_samples: int
    selected_samples: int
    projected_fallback_vertices: int
    neutral_fallback_vertices: int

@dataclass(frozen=True)
class ProjectedColorResult:
    color: tuple[float, float, float, float]
    used_fallback: bool
    total_samples: int
    candidate_samples: int
    source_rejected_samples: int
    visible_samples: int
    occluded_samples: int
    front_facing_samples: int
    backface_samples: int
    grazing_rejected_samples: int
    relative_rejected_samples: int
    top_k_rejected_samples: int
    selected_samples: int

    @property
    def accepted_samples(self) -> int:
        return self.selected_samples

    @property
    def rejected_samples(self) -> int:
        return max(0, self.total_samples - self.selected_samples)

@dataclass(frozen=True)
class _CandidateCollection:
    candidates: tuple[MaterialColorCandidate, ...]
    total_samples: int
    candidate_samples: int
    source_rejected_samples: int
    visible_samples: int
    occluded_samples: int
