"""Atomic multi-bone world-axis probes, independent of GLB importer bone rolls."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import asdict
import math

from mathutils import Vector
from mathutils.kdtree import KDTree

from scripts.glb_v2_pose_support import evaluated_positions, rotated_bone
from scripts.glb_v2_pose_metrics import joint_edge_summary
from scripts.glb_v2_combined_metrics import combined_cases, combined_summary, validate_sample_reference

_AXES = {"X": (1,0,0), "Y": (0,1,0), "Z": (0,0,1)}


@contextmanager
def rotated_chain(armature, rotations):
    """Validate the entire parent-first request before changing any bone."""
    rotations = tuple(rotations)
    names = [rotation.bone for rotation in rotations]
    if not names or len(set(names)) != len(names):
        raise ValueError("Combined pose needs distinct bones")
    for index, rotation in enumerate(rotations):
        if rotation.world_axis not in _AXES or not math.isfinite(rotation.degrees):
            raise ValueError("Invalid combined-pose rotation")
        if rotation.bone not in armature.pose.bones:
            raise ValueError(f"Missing combined-pose bone: {rotation.bone}")
        ancestor = armature.pose.bones[rotation.bone].parent
        while ancestor is not None:
            if ancestor.name in names[index+1:]:
                raise ValueError("Combined rotations must apply parents before children")
            ancestor = ancestor.parent
    with ExitStack() as stack:
        for rotation in rotations:
            stack.enter_context(rotated_bone(armature, rotation.bone, rotation.degrees,
                                            _AXES[rotation.world_axis], world_space=True))
        yield


def _sample_reference(rest, centers, height):
    # Deduplicate rest positions to avoid UV density bias, then select evenly
    # spaced entries near each joint and globally. At most 8*8+16 = 80 samples.
    if not math.isfinite(height) or height <= 0:
        raise ValueError("Combined-pose height must be positive and finite")
    unique = {}
    for point in rest:
        unique.setdefault(tuple(round(v/height,7) for v in point), point)
    ordered = sorted(unique)
    chosen = set()
    for keys, count in [(ordered,16), *[
        ([key for key in ordered if math.dist(unique[key],center) <= .12*height],8)
        for center in centers.values()
    ]]:
        if keys:
            sample_count = min(count,len(keys))
            chosen.update(keys[round(i*(len(keys)-1)/max(sample_count-1,1))] for i in range(sample_count))
    reference = {"height": height, "positions": [list(unique[key]) for key in sorted(chosen)]}
    validate_sample_reference(reference)
    return reference


def combined_quality(mesh, armature, regions, *, sample_reference=None):
    rest = evaluated_positions(mesh)
    height = max(p[2] for p in rest)-min(p[2] for p in rest)
    mesh.data.calc_loop_triangles()
    triangles = tuple(tuple(t.vertices) for t in mesh.data.loop_triangles)
    centers = {rotation.bone: tuple(armature.matrix_world @ armature.pose.bones[rotation.bone].head)
               for case in combined_cases() for rotation in case.rotations}
    if sample_reference is None:
        sample_reference = _sample_reference(rest,centers,height)
    validate_sample_reference(sample_reference)
    tree = KDTree(len(rest))
    for index, point in enumerate(rest):
        tree.insert(point,index)
    tree.balance()
    indices = []
    for point in sample_reference["positions"]:
        _, index, distance = tree.find(Vector(point))
        if distance > 1e-5*height:
            raise AssertionError("Cannot match combined-pose rest sample after GLB import")
        indices.append(index)
    cases = []
    for spec in combined_cases():
        with rotated_chain(armature,spec.rotations):
            posed = evaluated_positions(mesh)
        edges = {rotation.bone: joint_edge_summary(
            rest,posed,triangles,centers[rotation.bone],height,
            touching=rotation.bone.startswith(("forearm.","shin.")),
        ) for rotation in spec.rotations}
        response = {label: sum(math.dist(rest[i],posed[i]) for i in region)/len(region)/height
                    for label,region in regions.items()}
        samples = [[v/sample_reference["height"] for v in posed[index]] for index in indices]
        cases.append({"id": spec.identifier, "rotations": [asdict(r) for r in spec.rotations],
                      "joint_edges": edges, "region_response": response,
                      "sample_positions_in_heights": samples})
    return {"schema_version": 1, "scope": "36 stress poses; local edges and sampled geometry, not anatomy or collisions",
            "joint_radius_in_heights": .12, "sample_reference": sample_reference,
            **combined_summary(cases), "cases": cases}
