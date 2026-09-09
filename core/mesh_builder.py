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

    width = volume.width
    depth = volume.depth
    height = volume.height
    plane = width * depth
    values = volume.values

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    vertex_cache: dict[tuple[int, int, int], int] = {}

    def get_vertex(gx: int, gy: int, gz: int) -> int:
        key = (gx, gy, gz)
        existing = vertex_cache.get(key)
        if existing is not None:
            return existing

        index = len(vertices)
        vertices.append(
            (
                gx * voxel_size,
                gy * voxel_size,
                gz * voxel_size,
            )
        )
        vertex_cache[key] = index
        return index

    for index, occupied in enumerate(values):
        if not occupied:
            continue

        z, remainder = divmod(index, plane)
        y, x = divmod(remainder, width)

        left = x > 0 and values[index - 1]
        right = x + 1 < width and values[index + 1]
        back = y > 0 and values[index - width]
        front = y + 1 < depth and values[index + width]
        below = z > 0 and values[index - plane]
        above = z + 1 < height and values[index + plane]

        if not left:
            faces.append(
                (
                    get_vertex(x, y, z),
                    get_vertex(x, y, z + 1),
                    get_vertex(x, y + 1, z + 1),
                    get_vertex(x, y + 1, z),
                )
            )

        if not right:
            faces.append(
                (
                    get_vertex(x + 1, y, z),
                    get_vertex(x + 1, y + 1, z),
                    get_vertex(x + 1, y + 1, z + 1),
                    get_vertex(x + 1, y, z + 1),
                )
            )

        if not back:
            faces.append(
                (
                    get_vertex(x, y, z),
                    get_vertex(x + 1, y, z),
                    get_vertex(x + 1, y, z + 1),
                    get_vertex(x, y, z + 1),
                )
            )

        if not front:
            faces.append(
                (
                    get_vertex(x, y + 1, z),
                    get_vertex(x, y + 1, z + 1),
                    get_vertex(x + 1, y + 1, z + 1),
                    get_vertex(x + 1, y + 1, z),
                )
            )

        if not below:
            faces.append(
                (
                    get_vertex(x, y, z),
                    get_vertex(x, y + 1, z),
                    get_vertex(x + 1, y + 1, z),
                    get_vertex(x + 1, y, z),
                )
            )

        if not above:
            faces.append(
                (
                    get_vertex(x, y, z + 1),
                    get_vertex(x + 1, y, z + 1),
                    get_vertex(x + 1, y + 1, z + 1),
                    get_vertex(x, y + 1, z + 1),
                )
            )

    if center and vertices:
        center_x = volume.width * voxel_size * 0.5
        center_y = volume.depth * voxel_size * 0.5
        vertices = [
            (
                x - center_x,
                y - center_y,
                z,
            )
            for x, y, z in vertices
        ]

    return MeshData(
        vertices=tuple(vertices),
        faces=tuple(faces),
    )


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

    return MeshData(
        vertices=tuple(
            (
                x * scale,
                y * scale,
                (z - min_z) * scale,
            )
            for x, y, z in mesh.vertices
        ),
        faces=mesh.faces,
    )
