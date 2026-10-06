"""Explicit, fixture-specific ownership and sockets; not an anatomical heuristic.

The example's artist-authored planes deliberately keep existing whole faces.
They are not a universal partition implementation and never inspect skin weights.
"""

from __future__ import annotations


REGION_IDS = ("body-core", "left-arm", "right-arm", "left-leg", "right-leg")


def author_fixture_spec(geometry, rig, contract):
    mesh = geometry.blender_object
    points = [tuple(vertex.co) for vertex in mesh.data.vertices]
    polygons = [tuple(face.vertices) for face in mesh.data.polygons]
    floor = min(point[2] for point in points)
    height = max(point[2] for point in points) - floor
    center = (min(point[0] for point in points) + max(point[0] for point in points)) / 2
    # These are the declared design choices for this T-pose fixture only.
    arm_offset, hip_height = 0.15 * height, floor + 0.48 * height
    owners = []
    for face in polygons:
        x, _, z = tuple(sum(points[index][axis] for index in face) / len(face) for axis in range(3))
        if z < hip_height:
            owners.append("left-leg" if x >= center else "right-leg")
        elif x > center + arm_offset:
            owners.append("left-arm")
        elif x < center - arm_offset:
            owners.append("right-arm")
        else:
            owners.append("body-core")
    sockets = []
    # Complete, nonzero author transforms in exported joint-local coordinates.
    # A consumer multiplies joint_world * local_TRS; no reference-bone lengths.
    declarations = (
        ("attach-head", "head", "head", "body-core", (0, 0.20, 0)),
        ("attach-left-arm", "left-arm", "hand.L", "left-arm", (0.10, 0.15, 0)),
        ("attach-right-arm", "right-arm", "hand.R", "right-arm", (-0.10, 0.15, 0)),
        ("attach-left-leg", "left-leg", "foot.L", "left-leg", (0, 0.10, 0.12)),
        ("attach-right-leg", "right-leg", "foot.R", "right-leg", (0, 0.10, 0.12)),
        ("attach-back", "back", "chest", "body-core", (0, 0.10, -0.22)),
        ("attach-wing", "wing", "chest", "body-core", (0.20, 0.10, -0.18)),
        ("attach-backpack", "backpack", "spine", "body-core", (0, 0.10, -0.25)),
    )
    for socket_id, role, bone, region, translation in declarations:
        sockets.append(contract.SocketSpec(socket_id, role, bone, region, translation,
                                            (0, 0, 0, 1), (1, 1, 1)))
    spec = contract.ModularCharacterSpec(
        rig_id=rig.implementation_id, rig_version=2,
        coordinates=contract.CoordinateConvention(contract.NormalizationConvention(
            geometry.normalized_height, geometry.target_height, geometry.normalization_scale)),
        regions=tuple(contract.RegionSpec(region, region, f"MV_{region.replace('-', '_')}")
                      for region in REGION_IDS),
        ownership={mesh.name: tuple(owners)},
        ownership_source_sha256={mesh.name: contract.mesh_surface_sha256(points, polygons)},
        seams=contract.SeamDeclarations(), sockets=tuple(sockets),
    )
    choices = {"implementation": "fixture-authored-whole-face-planes-v1",
               "scope": "UAL1 native reconstruction T-pose only; not a generic anatomical classifier",
               "units": "source mesh local coordinates", "center_x": center,
               "arm_cut_x": [center - arm_offset, center + arm_offset], "hip_cut_z": hip_height,
               "tie_break": "whole polygon centroid, then left for center-plane ties",
               "boundary": "open-shared-vertices", "caps": 0}
    edge_owners = {}
    for face, owner in zip(polygons, owners):
        for first, second in zip(face, face[1:] + face[:1]):
            edge_owners.setdefault(tuple(sorted((first, second))), []).append(owner)
    choices["surface_coverage"] = {
        "source_polygon_count": len(polygons),
        "region_polygon_counts": {region: owners.count(region) for region in REGION_IDS},
        "unowned_source_polygons": 0, "duplicated_source_polygons": 0,
        "extra_cap_polygons": 0,
        "original_open_boundary_edges": sum(len(values) == 1 for values in edge_owners.values()),
        "original_nonmanifold_edges": sum(len(values) > 2 for values in edge_owners.values()),
        "new_inter_region_seam_edges": sum(len(set(values)) > 1 for values in edge_owners.values()),
    }
    return spec, choices
