"""Rest-surface observations, not aesthetic or watertightness certification."""

from collections import Counter
import math


def surface_observations(points, triangles):
    height = max(p[2] for p in points) - min(p[2] for p in points)
    if height <= 0:
        raise ValueError("Degenerate source surface")
    keys = [tuple(round(c / height, 8) for c in p) for p in points]
    edges = Counter()
    area = axis = volume = 0.0
    degenerate = 0
    for triangle in triangles:
        a, b, c = (points[i] for i in triangle)
        u = tuple(y - x for x, y in zip(a, b))
        v = tuple(y - x for x, y in zip(a, c))
        n = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        length = math.sqrt(sum(x * x for x in n))
        weight = 0.5 * length
        if length <= 1e-14:
            degenerate += 1
            continue
        area += weight
        if max(abs(x) / length for x in n) > 0.995:
            axis += weight
        volume += (
            sum(
                a[i]
                * (b[(i + 1) % 3] * c[(i + 2) % 3] - b[(i + 2) % 3] * c[(i + 1) % 3])
                for i in range(3)
            )
            / 6
        )
        k = [keys[i] for i in triangle]
        for x, y in zip(k, (*k[1:], k[0])):
            edges[tuple(sorted((x, y)))] += 1
    return dict(
        vertex_count=len(points),
        triangle_count=len(triangles),
        surface_area=area,
        axis_aligned_area_fraction=axis / area if area else None,
        degenerate_triangles=degenerate,
        boundary_edges=sum(n == 1 for n in edges.values()),
        nonmanifold_edges=sum(n > 2 for n in edges.values()),
        signed_volume_observation=volume,
        verification_status="unknown",
        topology_weld="coincident positions rounded in the same height-normalized frame; observation only",
        scope="Surface/topology diagnostics; no reference morphology or anatomical certificate",
    )
