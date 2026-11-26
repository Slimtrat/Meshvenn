"""Position correspondence across glTF seam splits, with topology validation."""

from collections import Counter, defaultdict
from itertools import product
import math


class PointIndex:
    def __init__(self, points, tolerance=2e-5):
        self.points = points
        self.tolerance = tolerance
        self.buckets = defaultdict(list)
        for i, p in enumerate(points):
            self.buckets[self.key(p)].append(i)

    def key(self, p):
        return tuple(math.floor(v / self.tolerance) for v in p)

    def nearest(self, p):
        key = self.key(p)
        choices = []
        for delta in product((-1, 0, 1), repeat=3):
            for i in self.buckets.get(tuple(a + b for a, b in zip(key, delta)), ()):
                d = math.dist(p, self.points[i])
                if d <= self.tolerance:
                    choices.append((d, i))
        if not choices:
            raise ValueError("Reloaded rest surface changed")
        distance = min(x[0] for x in choices)
        return sorted(i for d, i in choices if d <= distance + 1e-7)


def match_surface(
    reference, candidate, reference_triangles, candidate_triangles, weights
):
    source = PointIndex(reference)
    target = PointIndex(candidate)
    mapping = []
    for p in reference:
        choices = target.nearest(p)
        row = weights[choices[0]]
        for i in choices[1:]:
            if (
                max(
                    (
                        abs(row.get(n, 0.0) - weights[i].get(n, 0.0))
                        for n in row.keys() | weights[i].keys()
                    ),
                    default=0.0,
                )
                > 1e-5
            ):
                raise ValueError("Ambiguous skin weights at coincident export seams")
        mapping.append(choices[0])
    canonical = [min(source.nearest(p)) for p in reference]
    reverse = [min(source.nearest(p)) for p in candidate]

    def faces(triangles, ids):
        result = Counter()
        for tri in triangles:
            a, b, c = (ids[i] for i in tri)
            result[min((a, b, c), (b, c, a), (c, a, b))] += 1
        return result

    if faces(reference_triangles, canonical) != faces(candidate_triangles, reverse):
        raise ValueError("Reloaded oriented triangle surface changed")
    return mapping
