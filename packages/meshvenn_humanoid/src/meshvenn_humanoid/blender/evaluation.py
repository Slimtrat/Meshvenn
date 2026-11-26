"""Measured LBS behavior on exact GLB reloads; no renderer-only deformation."""

import math
import bpy
from mathutils import Vector
from .probes import evaluated_positions, rotated_bone


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return values[int(fraction * (len(values) - 1))]


def make_regions(mesh, rig, rest):
    height = max(p[2] for p in rest) - min(p[2] for p in rest)
    floor = min(p[2] for p in rest)
    center = (max(p[0] for p in rest) + min(p[0] for p in rest)) * 0.5
    regions = {}
    for side in ("L", "R"):
        upper = rig.data.bones["upper_arm." + side]
        fore = rig.data.bones["forearm." + side]
        s, e, w = (
            rig.matrix_world @ v
            for v in (upper.head_local, fore.head_local, fore.tail_local)
        )
        u = (e - s).normalized()
        v = (w - e).normalized()
        lu = (e - s).length
        lf = (w - e).length
        chain = {
            g.index
            for g in mesh.vertex_groups
            if g.name in ["upper_arm." + side, "forearm." + side, "hand." + side]
        }
        eligible = [
            x.index
            for x in mesh.data.vertices
            if sum(g.weight for g in x.groups if g.group in chain) > 0.6
        ]
        ring = [
            i
            for i in eligible
            if abs((Vector(rest[i]) - e).dot(v)) < 0.12 * min(lu, lf)
        ]
        # Only thickness in the tested flexion plane controls bend compression.
        # Lateral depth along the hinge axis does not need longitudinal blending.
        perpendicular = v.cross(Vector((0, 1, 0))).normalized()
        radii = [abs((Vector(rest[i]) - e).dot(perpendicular)) for i in ring]
        radius = percentile(radii, 0.95)
        if radius is None:
            raise ValueError("Unobserved elbow radius")
        half = 2.0 * radius
        prox = [
            i
            for i in eligible
            if 0.12 * lu < (Vector(rest[i]) - s).dot(u) < lu - 1.05 * half
        ]
        shoulder_rigid = [
            i
            for i in eligible
            if 0.30 * lu < (Vector(rest[i]) - s).dot(u) < lu - 1.05 * half
        ]
        distal = [i for i in eligible if (Vector(rest[i]) - e).dot(v) > 1.05 * half]
        sign = 1 if side == "L" else -1
        active = set(eligible)
        protected = [
            i
            for i, p in enumerate(rest)
            if i not in active
            and (
                p[2] < floor + 0.4 * height
                or p[2] > floor + 0.85 * height
                or abs(p[0] - center) < 0.025 * height
                or sign * (p[0] - center) < -0.10 * height
            )
        ]
        regions[side] = dict(
            proximal=prox,
            shoulder_rigid=shoulder_rigid,
            distal=distal,
            ring=ring,
            protected=protected,
            upper_length=lu,
            forearm_length=lf,
            elbow=tuple(e),
            observed_radius=radius,
            rigid_region_half_width=half,
        )
    return dict(height=height, sides=regions)


def measure(mesh, rig, regions, *, mapping=None, triangles=None, cancel=None):
    mapping = mapping if mapping is not None else list(range(len(mesh.data.vertices)))

    def positions():
        points = evaluated_positions(mesh)
        return [points[i] for i in mapping]

    rest = positions()
    height = regions["height"]
    probes = []
    if triangles is None:
        mesh.data.calc_loop_triangles()
        triangles = [tuple(t.vertices) for t in mesh.data.loop_triangles]
    group_names = {g.index: g.name for g in mesh.vertex_groups}
    for side, region in regions["sides"].items():
        prox, distal, ring, protected = (
            region[k] for k in ("proximal", "distal", "ring", "protected")
        )
        if min(map(len, (prox, distal, ring, protected))) < 4:
            raise ValueError("Insufficient fixed humanoid probe regions")
        elbow = Vector(region["elbow"])
        lu = region["upper_length"]
        lf = region["forearm_length"]
        ring_set = set(ring)
        local_faces = [t for t in triangles if any(i in ring_set for i in t)]
        child_weights = [
            sum(
                g.weight
                for g in mesh.data.vertices[i].groups
                if group_names[g.group] in ("forearm." + side, "hand." + side)
            )
            for i in mapping
        ]
        for family, angles in (("forearm", (45, 90)), ("upper_arm", (45, 70))):
            for angle in angles:
                if cancel and cancel():
                    raise InterruptedError("Humanoid analysis cancelled")
                bone = family + "." + side
                with rotated_bone(
                    rig,
                    bone,
                    angle if side == "L" else -angle,
                    (0, 1, 0),
                    world_space=True,
                ):
                    posed = positions()
                    pb = rig.pose.bones[bone]
                    delta = (
                        rig.matrix_world
                        @ pb.matrix
                        @ pb.bone.matrix_local.inverted()
                        @ rig.matrix_world.inverted()
                    )

                    def error(indices, transform, scale):
                        return (
                            max(
                                (Vector(posed[i]) - transform(Vector(rest[i]))).length
                                for i in indices
                            )
                            / scale
                        )

                    row = dict(
                        bone=bone,
                        degrees=angle,
                        protected_error=error(protected, lambda v: v, height),
                        distal_error=error(distal, lambda v: delta @ v, lf),
                    )
                    if family == "forearm":
                        row["proximal_error"] = error(prox, lambda v: v, lu)
                        row["radius_retention"] = percentile(
                            [
                                math.dist(posed[i], elbow) / math.dist(rest[i], elbow)
                                for i in ring
                                if math.dist(rest[i], elbow) > 1e-8
                            ],
                            0.05,
                        )
                        area = []
                        inverted = total_area = 0.0
                        for a, b, c in local_faces:
                            normal = (Vector(rest[b]) - Vector(rest[a])).cross(
                                Vector(rest[c]) - Vector(rest[a])
                            )
                            changed_normal = (
                                Vector(posed[b]) - Vector(posed[a])
                            ).cross(Vector(posed[c]) - Vector(posed[a]))
                            before = normal.length
                            after = changed_normal.length
                            if before > 1e-14:
                                area.append(after / before)
                                total_area += before
                                weight = (
                                    child_weights[a]
                                    + child_weights[b]
                                    + child_weights[c]
                                ) / 3
                                expected = (1.0 - weight) * normal + weight * (
                                    delta.to_3x3() @ normal
                                )
                                if (
                                    after > 1e-14
                                    and expected.length > 1e-14
                                    and changed_normal.normalized().dot(
                                        expected.normalized()
                                    )
                                    < -1e-5
                                ):
                                    inverted += before
                        row["area_retention"] = percentile(area, 0.01)
                        row["inverted_area_fraction"] = (
                            inverted / total_area if total_area else None
                        )
                    else:
                        if len(region["shoulder_rigid"]) < 4:
                            raise ValueError("Insufficient fixed shoulder region")
                        row["proximal_error"] = error(
                            region["shoulder_rigid"], lambda v: delta @ v, lu
                        )
                    probes.append(row)
    restoration = max(math.dist(a, b) for a, b in zip(rest, positions()))
    if restoration > 1e-6:
        raise ValueError("Probe failed to restore source rest pose")
    elbows = [r for r in probes if r["bone"].startswith("forearm.")]
    shoulders = [r for r in probes if r["bone"].startswith("upper_arm.")]
    return dict(
        proximal_link_error=max(r["proximal_error"] for r in elbows),
        distal_link_error=max(r["distal_error"] for r in elbows),
        protected_elbow_error=max(r["protected_error"] for r in elbows),
        shoulder_link_error=max(
            max(r["proximal_error"], r["distal_error"]) for r in shoulders
        ),
        protected_shoulder_error=max(r["protected_error"] for r in shoulders),
        elbow_radius_retention=min(r["radius_retention"] for r in elbows),
        elbow_area_retention=min(r["area_retention"] for r in elbows),
        elbow_inverted_area_fraction=max(r["inverted_area_fraction"] for r in elbows),
    ), dict(
        probes=probes,
        rest_restore_error=restoration,
        region_counts={
            s: {k: len(v) for k, v in r.items() if isinstance(v, list)}
            for s, r in regions["sides"].items()
        },
    )
