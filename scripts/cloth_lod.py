"""Author a bounded source LOD of the frozen cloth dummy, outside engine policy.

This is a producer operation on a disposable Blender copy. A passing geometric
budget does not select a skin or imply consumer, visual, physics or rights approval.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
sys.path.insert(0, str(ROOT))
from meshvenn_humanoid.blender import source
from meshvenn_humanoid.observations import surface_observations
from scripts.author_stytch_doll import source_snapshot

SOURCE_SHA256 = "5f4c2730c8a5be475d68462e38d1d054fe8fedb0d4f0d476707421276febe1f5"
REFERENCE_SHA256 = "c5d79f03057fe84264a1fa9231bc31e71f42c971324ae0a08009c339b760b65d"
POLICY = {
    "schema_version": 1,
    "algorithm": "cloth-source-deformation-protected-collapse-v5",
    "max_triangles": 18000,
    "max_sampled_surface_error_m": 0.005,
    "p99_sampled_surface_error_m": 0.002,
    "max_pruned_skin_mass": 0.03,
    "minimum_portable_weight": 1.01e-4,
    "max_boundary_edge_increase": 0,
    "max_nonmanifold_edge_increase": 0,
    "ratio": 0.44,
    "edge_risk_mass": 0.005,
    "edge_weight_gradient": 0.06,
    "protection_factor": 1000,
    "invert_protection": True,
    "max_feedback_vertices": 2048,
    "pose_replay_required": True,
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", "utf-8")


def surface(mesh):
    mesh.data.calc_loop_triangles()
    return (
        [tuple(mesh.matrix_world @ v.co) for v in mesh.data.vertices],
        [tuple(t.vertices) for t in mesh.data.loop_triangles],
    )


def samples(points, triangles):
    yield from points
    for triangle in triangles:
        yield tuple(sum(points[i][axis] for i in triangle) / 3 for axis in range(3))


def sampled_distance(reference, candidate, *, protect_above=None):
    """Both directions: all vertices and face centers to actual triangle surfaces.

    This is a finite sample, not a continuous Hausdorff or silhouette proof.
    """
    distances, protection = [], set()
    for direction, (left, right) in enumerate(
        ((reference, candidate), (candidate, reference))
    ):
        tree = BVHTree.FromPolygons(*right, all_triangles=True)
        for index, point in enumerate(samples(*left)):
            nearest = tree.find_nearest(Vector(point))
            if nearest[3] is None:
                raise ValueError("Cannot measure an empty or invalid surface")
            distances.append(nearest[3])
            if protect_above is not None and nearest[3] > protect_above:
                if direction == 0:
                    protection.update(
                        (index,)
                        if index < len(left[0])
                        else left[1][index - len(left[0])]
                    )
                else:
                    protection.update(reference[1][nearest[2]])
    distances.sort()
    result = {
        "max": distances[-1],
        "p99": distances[int(0.99 * (len(distances) - 1))],
        "samples": len(distances),
    }
    if protect_above is not None:
        result["feedback_source_vertices"] = sorted(protection)
    return result


def protected_vertices(edges, weights, threshold, gradient=0.06, extra=()):
    """Protect edges whose averaged skin could lose a fifth strong influence."""
    edges = tuple(tuple(edge) for edge in edges)
    risk = set()
    for edge in edges:
        a, b = (weights[i] for i in edge)
        combined = sorted(
            ((a.get(name, 0) + b.get(name, 0)) / 2 for name in a.keys() | b.keys()),
            reverse=True,
        )
        if (
            sum(combined[4:]) > threshold
            or max(abs(a.get(name, 0) - b.get(name, 0)) for name in a.keys() | b.keys())
            > gradient
        ):
            risk.update(edge)
    risk.update(extra)
    initial = set(risk)
    risk.update(v for edge in edges if set(edge) & initial for v in edge)
    return risk


def prune_weights(weights):
    result, loss = [], 0.0
    for row in weights:
        # Blender's glTF writer omits tiny influences. Make that intentional in
        # source authoring BEFORE fidelity probes, measuring their lost mass.
        kept = sorted(
            (
                (name, value)
                for name, value in row.items()
                if value > POLICY["minimum_portable_weight"]
            ),
            key=lambda item: (-item[1], item[0]),
        )[:4]
        total = sum(value for _, value in kept)
        if total <= 0:
            raise ValueError("LOD contains an unbound vertex")
        loss = max(loss, max(0.0, sum(row.values()) - total))
        result.append({name: value / total for name, value in kept if value > 0})
    return result, loss


def transfer_weights(reference, weights, points):
    """Sample the original continuous triangle skin field, not collapse history."""
    vertices, triangles = reference
    tree = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
    result = []
    for point in points:
        nearest, _, face, _ = tree.find_nearest(Vector(point))
        if face is None:
            raise ValueError("No source surface for LOD skin transfer")
        indices = triangles[face]
        a, b, c = (Vector(vertices[i]) for i in indices)
        u, v, p = b - a, c - a, nearest - a
        uu, uv, vv = u.dot(u), u.dot(v), v.dot(v)
        denominator = uu * vv - uv * uv
        if denominator <= 1e-28:
            raise ValueError("Degenerate source triangle in skin transfer")
        beta = (vv * p.dot(u) - uv * p.dot(v)) / denominator
        gamma = (uu * p.dot(v) - uv * p.dot(u)) / denominator
        barycentric = [max(0.0, 1 - beta - gamma), max(0.0, beta), max(0.0, gamma)]
        total = sum(barycentric)
        row = {}
        for i, coefficient in zip(indices, barycentric):
            for name, value in weights[i].items():
                row[name] = row.get(name, 0.0) + coefficient / total * value
        result.append(row)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--feedback",
        type=Path,
        help="Retained failed pose report; protects its exact source vertices",
    )
    args = parser.parse_args(
        argv if argv is not None else sys.argv[sys.argv.index("--") + 1 :]
    )
    original = args.source.resolve(strict=True)
    output = args.output.resolve()
    if source.digest(original) != SOURCE_SHA256:
        raise ValueError(
            "This authoring recipe only applies to the exact frozen native cloth source"
        )
    output.mkdir(parents=True, exist_ok=False)
    policy = dict(POLICY)
    extra = []
    if args.feedback:
        feedback = json.loads(args.feedback.read_text("utf-8"))
        extra = feedback["feedback_source_vertices"]
        if (
            feedback["source_sha256"] != SOURCE_SHA256
            or feedback["fidelity_passed"] is not False
            or not extra
            or len(extra) > POLICY["max_feedback_vertices"]
            or len(set(extra)) != len(extra)
            or any(type(i) is not int or i < 0 for i in extra)
        ):
            raise ValueError(
                "Feedback is not a bounded failed report for this exact source"
            )
        if (
            feedback["budget"]["max_sampled_surface_error_m"]
            != POLICY["max_sampled_surface_error_m"]
            or feedback["budget"]["p99_sampled_surface_error_m"]
            != POLICY["p99_sampled_surface_error_m"]
        ):
            raise ValueError("Feedback was produced under a different fidelity budget")
        policy["feedback_sha256"] = source.digest(args.feedback)
        policy["feedback_source_vertices"] = extra
    write_json(output / "budget.json", policy)
    mesh, rig = source.load(original)
    if rig is None:
        raise ValueError("The pinned source lost its single native armature")
    before = source_snapshot(mesh, rig)
    if any(i >= len(mesh.data.vertices) for i in extra):
        raise ValueError("Feedback vertex lies outside the frozen source")
    reference = surface(mesh)
    initial = surface_observations(*reference)
    original_weights = source.weights(mesh)
    risk = protected_vertices(
        (e.vertices for e in mesh.data.edges),
        original_weights,
        POLICY["edge_risk_mass"],
        POLICY["edge_weight_gradient"],
        extra,
    )
    temporary = "Cloth LOD protection (temporary)"
    if temporary in mesh.vertex_groups:
        raise ValueError("Reserved protection group already exists")
    group = mesh.vertex_groups.new(name=temporary)
    if risk:
        group.add(sorted(risk), 1, "REPLACE")
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    decimate = mesh.modifiers.new("Cloth source LOD", "DECIMATE")
    decimate.decimate_type = "COLLAPSE"
    decimate.ratio = POLICY["ratio"]
    decimate.use_collapse_triangulate = True
    decimate.vertex_group = temporary
    decimate.vertex_group_factor = POLICY["protection_factor"]
    decimate.invert_vertex_group = POLICY["invert_protection"]
    bpy.ops.object.modifier_move_up(modifier=decimate.name)
    bpy.ops.object.modifier_apply(modifier=decimate.name)
    # Applying a modifier invalidates cached group RNA references.
    mesh.vertex_groups.remove(mesh.vertex_groups[temporary])
    current = surface(mesh)
    bounded, loss = prune_weights(
        transfer_weights(reference, original_weights, current[0])
    )
    source.apply_weights(mesh, bounded)
    observation = surface_observations(*current)
    error = sampled_distance(reference, current)
    after = source_snapshot(mesh, rig)
    authority = (
        "bones",
        "rig_world",
        "world",
        "material_pixels",
        "material_signatures",
    )
    preserved = all(before[key] == after[key] for key in authority)
    checks = {
        "triangle_budget": len(current[1]) <= POLICY["max_triangles"],
        "sampled_surface_max": error["max"] <= POLICY["max_sampled_surface_error_m"],
        "sampled_surface_p99": error["p99"] <= POLICY["p99_sampled_surface_error_m"],
        "pruned_mass": loss <= POLICY["max_pruned_skin_mass"],
        "boundaries": observation["boundary_edges"] <= initial["boundary_edges"],
        "nonmanifold": observation["nonmanifold_edges"] <= initial["nonmanifold_edges"],
        "rest_rig_frames_and_materials": preserved,
    }
    report = {
        "source_blend_sha256": SOURCE_SHA256,
        "reference_glb_sha256": REFERENCE_SHA256,
        "policy": policy,
        "source": initial,
        "candidate": observation,
        "protected_vertices": len(risk),
        "max_pruned_skin_mass": loss,
        "sampled_surface_distance_m": error,
        "checks": checks,
        "rest_fidelity_passed": all(checks.values()),
        "selected": False,
        "visual_acceptance": False,
        "consumer_admission": False,
        "skin_transfer": "Nearest original triangle, nonnegative normalized barycentric weights, then measured top-four pruning; decimator weight interpolation discarded",
        "scope": "Source LOD approximation only; existing source creases/topology observations remain disclosed. UVs are interpolated by collapse, not rebaked. No renderer, collider or licence admission.",
    }
    mesh["meshvenn_cloth_lod"] = json.dumps(report, sort_keys=True, allow_nan=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"), compress=True)
    report["candidate_blend_sha256"] = source.digest(output / "source.blend")
    write_json(output / "lod.json", report)
    if source.digest(original) != SOURCE_SHA256:
        raise ValueError("Immutable source changed during authoring")
    if not report["rest_fidelity_passed"]:
        raise ValueError(
            "Candidate retained with failed LOD budget; do not export or select it"
        )
    print(
        f"Rest LOD fidelity PASS: {len(current[1])} triangles; pose/visual/consumer acceptance still required"
    )


if __name__ == "__main__":
    main()
