"""Non-destructive face selection; anatomical ownership is never guessed."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .ownership import validated_polygons
from .validation import identifier, sequence, unique


@dataclass(frozen=True)
class FacePartition:
    region_faces: object
    region_vertices: object
    shared_vertices: object
    boundary_edges: object


def partition_faces(polygons, ownership, region_ids, *, vertex_count):
    """Return source index selections and declared open boundary/seam topology.

    No vertex, face, weight, loop attribute or material is changed. A vertex may
    belong to several regions but every polygon belongs to exactly one region.
    Boundary edges include existing open borders and borders exposed by splitting.
    """
    faces = validated_polygons(polygons, vertex_count=vertex_count)
    owners = tuple(identifier(owner, name="face region id")
                   for owner in sequence(ownership, name="ownership"))
    regions = tuple(identifier(region, name="region id")
                    for region in sequence(region_ids, name="region_ids"))
    unique(regions, name="region ids")
    if len(owners) != len(faces) or not regions:
        raise ValueError("Every polygon requires exactly one owner and regions cannot be empty.")
    if set(owners) != set(regions):
        raise ValueError("Ownership must use every declared region and no unknown regions.")
    by_region = {region: [] for region in regions}
    vertices = {region: set() for region in regions}
    vertex_owners = {}
    edge_faces = {region: {} for region in regions}
    for index, (face, owner) in enumerate(zip(faces, owners)):
        by_region[owner].append(index)
        vertices[owner].update(face)
        for vertex in face:
            vertex_owners.setdefault(vertex, set()).add(owner)
        for first, second in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((first, second)))
            edge_faces[owner][edge] = edge_faces[owner].get(edge, 0) + 1
    return FacePartition(
        MappingProxyType({region: tuple(indices) for region, indices in by_region.items()}),
        MappingProxyType({region: tuple(sorted(indices)) for region, indices in vertices.items()}),
        MappingProxyType({vertex: tuple(sorted(owners)) for vertex, owners in sorted(vertex_owners.items())
                          if len(owners) > 1}),
        MappingProxyType({region: tuple(sorted(edge for edge, count in edges.items() if count == 1))
                          for region, edges in edge_faces.items()}))
