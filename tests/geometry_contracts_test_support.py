from __future__ import annotations

from types import SimpleNamespace

from core.geometry_contracts import GeometryProjectionSpace, GeometrySurfaceOutput


class FakeMeshData:

    def __init__(self, *, vertex_count: int = 4, polygon_count: int = 2) -> None:
        self.vertices = [object() for _ in range(vertex_count)]
        self.polygons = [object() for _ in range(polygon_count)]


class FakeBlenderObject:

    def __init__(
        self,
        *,
        name: str = "FakeGeometry",
        vertex_count: int = 4,
        polygon_count: int = 2,
    ) -> None:
        self.name = name
        self.type = "MESH"
        self.data = FakeMeshData(vertex_count=vertex_count, polygon_count=polygon_count)


class FakeSDFGeometryOutput(GeometrySurfaceOutput):
    """
    Deliberately NOT a NativeVisualHullOutput.

    This represents the kind of subtype a future
    sdf-reconstruction-v1 implementation will return.
    """

    pass


def projection_space(
    *,
    width: int = 32,
    depth: int = 48,
    height: int = 64,
    voxel_size: float = 0.5,
    center_xy: bool = True,
) -> GeometryProjectionSpace:
    return GeometryProjectionSpace(
        width=width,
        depth=depth,
        height=height,
        voxel_size=voxel_size,
        center_xy=center_xy,
    )


def geometry_output(
    *,
    implementation_id: str = "sdf-reconstruction-v1",
    width: int = 32,
    depth: int = 48,
    height: int = 64,
    voxel_size: float = 0.5,
    center_xy: bool = True,
    metrics=None,
    metadata=None,
) -> GeometrySurfaceOutput:
    source = SimpleNamespace(material_views=("front", "side"))
    return GeometrySurfaceOutput(
        blender_object=FakeBlenderObject(),
        source=source,
        projection_space=projection_space(
            width=width,
            depth=depth,
            height=height,
            voxel_size=voxel_size,
            center_xy=center_xy,
        ),
        implementation_id=implementation_id,
        metrics=metrics or {},
        metadata=metadata or {},
    )
