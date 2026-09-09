from __future__ import annotations

from dataclasses import dataclass

from .visual_hull import VoxelVolume


@dataclass(frozen=True)
class MeshData:
    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, int, int, int], ...]

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def face_count(self) -> int:
        return len(self.faces)


def build_surface_mesh(
    volume: VoxelVolume,
    *,
    voxel_size: float = 1.0,
    center: bool = True,
) -> MeshData:
    if voxel_size <= 0.0:
        raise ValueError("Voxel size must be greater than zero.")

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []

    vertex_cache: dict[
        tuple[int, int, int],
        int,
    ] = {}

    def get_vertex(
        gx: int,
        gy: int,
        gz: int,
    ) -> int:
        key = (gx, gy, gz)

        existing = vertex_cache.get(key)

        if existing is not None:
            return existing

        x = gx * voxel_size
        y = gy * voxel_size
        z = gz * voxel_size

        index = len(vertices)

        vertices.append((x, y, z))
        vertex_cache[key] = index

        return index

    for z in range(volume.height):
        for y in range(volume.depth):
            for x in range(volume.width):
                if not volume.get(x, y, z):
                    continue

                _append_exposed_faces(
                    volume=volume,
                    x=x,
                    y=y,
                    z=z,
                    get_vertex=get_vertex,
                    faces=faces,
                )

    if center and vertices:
        vertices = _center_vertices(
            vertices,
            volume=volume,
            voxel_size=voxel_size,
        )

    return MeshData(
        vertices=tuple(vertices),
        faces=tuple(faces),
    )


def _append_exposed_faces(
    *,
    volume: VoxelVolume,
    x: int,
    y: int,
    z: int,
    get_vertex,
    faces: list[tuple[int, int, int, int]],
) -> None:
    # -X
    if not volume.get(x - 1, y, z):
        faces.append(
            (
                get_vertex(x, y, z),
                get_vertex(x, y, z + 1),
                get_vertex(x, y + 1, z + 1),
                get_vertex(x, y + 1, z),
            )
        )

    # +X
    if not volume.get(x + 1, y, z):
        faces.append(
            (
                get_vertex(x + 1, y, z),
                get_vertex(x + 1, y + 1, z),
                get_vertex(x + 1, y + 1, z + 1),
                get_vertex(x + 1, y, z + 1),
            )
        )

    # -Y
    if not volume.get(x, y - 1, z):
        faces.append(
            (
                get_vertex(x, y, z),
                get_vertex(x + 1, y, z),
                get_vertex(x + 1, y, z + 1),
                get_vertex(x, y, z + 1),
            )
        )

    # +Y
    if not volume.get(x, y + 1, z):
        faces.append(
            (
                get_vertex(x, y + 1, z),
                get_vertex(x, y + 1, z + 1),
                get_vertex(x + 1, y + 1, z + 1),
                get_vertex(x + 1, y + 1, z),
            )
        )

    # -Z
    if not volume.get(x, y, z - 1):
        faces.append(
            (
                get_vertex(x, y, z),
                get_vertex(x, y + 1, z),
                get_vertex(x + 1, y + 1, z),
                get_vertex(x + 1, y, z),
            )
        )

    # +Z
    if not volume.get(x, y, z + 1):
        faces.append(
            (
                get_vertex(x, y, z + 1),
                get_vertex(x + 1, y, z + 1),
                get_vertex(x + 1, y + 1, z + 1),
                get_vertex(x, y + 1, z + 1),
            )
        )


def _center_vertices(
    vertices: list[tuple[float, float, float]],
    *,
    volume: VoxelVolume,
    voxel_size: float,
) -> list[tuple[float, float, float]]:
    center_x = volume.width * voxel_size * 0.5
    center_y = volume.depth * voxel_size * 0.5

    # On garde les pieds sur Z = 0.
    # Donc seul X/Y est centré.
    return [
        (
            x - center_x,
            y - center_y,
            z,
        )
        for x, y, z in vertices
    ]


def scale_mesh_to_height(
    mesh: MeshData,
    target_height: float,
) -> MeshData:
    if target_height <= 0.0:
        raise ValueError("Target height must be greater than zero.")

    if not mesh.vertices:
        return mesh

    min_z = min(vertex[2] for vertex in mesh.vertices)
    max_z = max(vertex[2] for vertex in mesh.vertices)

    current_height = max_z - min_z

    if current_height <= 0.0:
        return mesh

    scale = target_height / current_height

    scaled_vertices = tuple(
        (
            x * scale,
            y * scale,
            (z - min_z) * scale,
        )
        for x, y, z in mesh.vertices
    )

    return MeshData(
        vertices=scaled_vertices,
        faces=mesh.faces,
    )