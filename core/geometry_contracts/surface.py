from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..pipeline_contracts import validate_implementation_id
from .projection import GeometryProjectionSpace


def _normalize_mapping(value: Mapping[str, Any] | None, *, name: str) -> dict[str, Any]:
    """
    Normalize flexible implementation metrics/metadata.

    Values remain intentionally unrestricted because they
    may contain implementation-specific diagnostics.

    Keys must however remain stable strings so manifests and
    debug tooling can consume them consistently.
    """
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping.")
    result: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError(f"{name} cannot contain an empty key.")
        result[normalized_key] = item
    return result


@dataclass(frozen=True)
class GeometrySurfaceOutput:
    """
    Generic contract returned by a Meshvenn GEOMETRY stage.

    Concrete geometry implementations may subclass this
    object and expose additional implementation-specific
    fields.

    Examples:

        NativeVisualHullOutput(
            ...
        )

        SDFReconstructionOutput(
            ...
        )

    Downstream stages should depend only on this base
    contract whenever possible.

    In particular MATERIAL, RIG and EXPORT should not need
    to know whether the geometry came from:

        visual hull
        SDF
        neural reconstruction
        imported mesh
        another future engine

    -------------------------------------------------------
    blender_object
    -------------------------------------------------------

    The surface object produced by GEOMETRY.

    The type is deliberately Any so this core module remains
    importable without bpy.

    Blender implementations will normally provide:

        bpy.types.Object

    Pure Python tests may provide a lightweight fake object.

    -------------------------------------------------------
    source
    -------------------------------------------------------

    INPUT-stage data from which this geometry was produced.

    The generic geometry contract intentionally does not
    require ProjectionImagesOutput specifically.

    Future INPUT implementations may provide other source
    types.

    -------------------------------------------------------
    projection_space
    -------------------------------------------------------

    Coordinate system required to project mesh-local surface
    positions back into the original views.

    This is the critical bridge between interchangeable
    GEOMETRY and MATERIAL implementations.

    -------------------------------------------------------
    implementation_id
    -------------------------------------------------------

    Stable implementation identifier, for example:

        native-visual-hull
        sdf-reconstruction-v1

    -------------------------------------------------------
    metrics / metadata
    -------------------------------------------------------

    Generic extension points for diagnostics.

    metrics:
        primarily numeric execution/output measurements.

    metadata:
        descriptive implementation information.

    These mappings must never be required by downstream
    algorithms for fundamental coordinate reconstruction.
    Fundamental geometry state belongs in explicit fields.
    """

    blender_object: Any
    source: Any
    projection_space: GeometryProjectionSpace
    implementation_id: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.blender_object is None:
            raise ValueError("GeometrySurfaceOutput requires a surface object.")
        if self.source is None:
            raise ValueError("GeometrySurfaceOutput requires its INPUT source.")
        if not isinstance(self.projection_space, GeometryProjectionSpace):
            raise TypeError("projection_space must be a GeometryProjectionSpace.")
        implementation_id = validate_implementation_id(self.implementation_id)
        object.__setattr__(self, "implementation_id", implementation_id)
        object.__setattr__(
            self, "metrics", _normalize_mapping(self.metrics, name="metrics")
        )
        object.__setattr__(
            self, "metadata", _normalize_mapping(self.metadata, name="metadata")
        )

    @property
    def width(self) -> int:
        return self.projection_space.width

    @property
    def depth(self) -> int:
        return self.projection_space.depth

    @property
    def height(self) -> int:
        return self.projection_space.height

    @property
    def voxel_size(self) -> float:
        return self.projection_space.voxel_size

    @property
    def center_xy(self) -> bool:
        return self.projection_space.center_xy

    @property
    def projection_dimensions(self) -> tuple[int, int, int]:
        return self.projection_space.dimensions

    @property
    def object_name(self) -> str:
        name = getattr(self.blender_object, "name", None)
        if name is None:
            return type(self.blender_object).__name__
        return str(name)

    @property
    def vertex_count(self) -> int | None:
        """
        Best-effort generic vertex count.

        Explicit metrics win.

        Blender-specific inspection is only attempted through
        attribute access so this module remains bpy-free.
        """
        if "vertex_count" in self.metrics:
            try:
                return int(self.metrics["vertex_count"])
            except (TypeError, ValueError):
                pass
        data = getattr(self.blender_object, "data", None)
        vertices = getattr(data, "vertices", None)
        if vertices is None:
            return None
        try:
            return len(vertices)
        except TypeError:
            return None

    @property
    def polygon_count(self) -> int | None:
        """
        Best-effort generic polygon count.
        """
        if "polygon_count" in self.metrics:
            try:
                return int(self.metrics["polygon_count"])
            except (TypeError, ValueError):
                pass
        data = getattr(self.blender_object, "data", None)
        polygons = getattr(data, "polygons", None)
        if polygons is None:
            return None
        try:
            return len(polygons)
        except TypeError:
            return None

    def projection_kwargs(self) -> dict[str, Any]:
        return self.projection_space.as_projection_kwargs()
