"""Pure deformation metrics for an explicitly bounded head/neck probe cohort."""
import math


def masked_edge_summary(rest, posed, triangles, mask, height):
    if (not rest or len(rest) != len(posed) or len(mask) != len(rest)
            or not math.isfinite(height) or height <= 0
            or any(type(v) is not bool for v in mask)
            or any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in (*rest, *posed))):
        raise ValueError("Expected finite unchanged 3D topology and an explicit Boolean cohort.")
    origin = tuple(min(p[i] for p in rest) for i in range(3))
    keys = [tuple(round((v-o)/height, 7) for v,o in zip(p, origin)) for p in rest]
    edges = {}
    for triangle in triangles:
        if len(triangle) != 3 or any(type(i) is not int or not 0 <= i < len(rest) for i in triangle):
            raise ValueError("Invalid triangle.")
        for a, b in zip(triangle, (*triangle[1:], triangle[0])):
            if not mask[a] or not mask[b]:
                continue
            length = math.dist(rest[a], rest[b])
            if length <= height*1e-5:
                continue
            ratio = math.dist(posed[a], posed[b])/length
            strain = abs(math.log(max(ratio, 1e-12)))
            key = tuple(sorted((keys[a], keys[b])))
            if key not in edges or strain > edges[key][0]:
                edges[key] = (strain, ratio)
    if not edges:
        raise ValueError("Empty nondegenerate cohort cannot qualify deformation.")
    strains = sorted(v[0] for v in edges.values())
    ratios = [v[1] for v in edges.values()]
    return {"edge_count": len(edges), "p95_abs_log_length_ratio": strains[math.ceil(.95*len(strains))-1],
            "max_abs_log_length_ratio": strains[-1], "min_length_ratio": min(ratios),
            "max_length_ratio": max(ratios), "outside_20_percent_count": sum(r < .8 or r > 1.2 for r in ratios),
            "collapsed_fraction": sum(r < .25 for r in ratios)/len(ratios)}


def rigid_residual(rest, posed, expected, mask, height):
    if (not rest or not len(rest) == len(posed) == len(expected) == len(mask)
            or not math.isfinite(height) or height <= 0 or not any(mask)
            or any(type(v) is not bool for v in mask)
            or any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in (*rest, *posed, *expected))):
        raise ValueError("Rigid residual requires a finite nonempty unchanged cohort.")
    values = [math.dist(p, q)/height for p,q,selected in zip(posed, expected, mask) if selected]
    return {"vertex_count": len(values), "max_residual_in_heights": max(values),
            "mean_residual_in_heights": sum(values)/len(values)}
