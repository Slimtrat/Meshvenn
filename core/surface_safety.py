"""Local face safeguards for bounded surface fitting (exact float32 output)."""
from array import array
import math


def _normal(points, tri):
    a, b, c = (points[i] for i in tri)
    u, v = [b[k]-a[k] for k in range(3)], [c[k]-a[k] for k in range(3)]
    return (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def constrain_faces(original, candidates, triangles, limit):
    """Back off only unsafe neighborhoods, not the whole connected character.

    The existing component-level volume/orientation check still runs afterwards.
    This avoids a single tiny triangle reducing the finish on all other limbs.
    """
    points = []
    for anchor, candidate in zip(original, candidates):
        q = tuple(array('f', candidate))
        for _ in range(8):
            distance = math.dist(q, anchor)
            if distance <= limit:
                break
            factor = min(.999999, limit/distance*.999999)
            q = tuple(array('f', (anchor[k]+(q[k]-anchor[k])*factor for k in range(3))))
        else:
            q = anchor
        points.append(q)
    normals = [_normal(original, tri) for tri in triangles]
    limited = set()
    for attempt in range(25):
        unsafe = {i for tri, n in zip(triangles, normals)
                  if _dot(_normal(points, tri), n) < .1*_dot(n, n) for i in tri}
        if not unsafe:
            return points, len(limited)
        limited.update(unsafe)
        for i in sorted(unsafe):
            factor = .5 if attempt < 24 else 0.
            points[i] = tuple(array('f', (original[i][k]+factor*(points[i][k]-original[i][k])
                                         for k in range(3))))
    # A subsequent component guard is authoritative if float32 precision left
    # an unsafe face at the edge of a reverted neighborhood.
    return points, len(limited)
