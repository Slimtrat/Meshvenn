"""Keep distant authored limb skin on its existing native chain only."""
from __future__ import annotations

import math

from .canonical_rig import bounds_from_vertices
from .modular_character import partition_faces
from .native_pose_probe import PARENTS
from .rig_owned_skin import DEFORM, ROLES, _bounded, _smooth, _surface_distances

ALGORITHM = "authored-distal-native-chains-v1"
CHAINS = {"left-arm": ("upper_arm.L", "forearm.L", "hand.L"),
          "right-arm": ("upper_arm.R", "forearm.R", "hand.R"),
          "left-leg": ("thigh.L", "shin.L", "foot.L"),
          "right-leg": ("thigh.R", "shin.R", "foot.R")}


def refine_distal_limb_weights(vertices, polygons, roles, weights, bones, *, collar_in_heights=.06):
    """Project onto existing chain ratios, fading only beyond the source collar.

    Never invent a missing native influence, move a joint or relabel anatomy.
    Body/interface weights and already chain-only rows stay bit-for-bit intact.
    At two preceding collar widths, positive foreign influence is exactly zero.
    """
    points = tuple(tuple(p) for p in vertices)
    if (not points or len(points) != len(weights)
            or any(len(p) != 3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in points)
            or type(collar_in_heights) not in (int,float) or not math.isfinite(collar_in_heights)
            or not .02 <= collar_in_heights <= .08):
        raise ValueError("Require finite original vertices, matching native weights and the preceding source collar.")
    bounds = bounds_from_vertices(points)
    faces, roles = tuple(tuple(f) for f in polygons), tuple(roles)
    partition_faces(faces,roles,sorted(ROLES),vertex_count=len(points))
    if {i for f in faces for i in f} != set(range(len(points))):
        raise ValueError("Unused vertices cannot define limb geodesics.")
    bones = tuple(bones)
    by_name = {b.name:b for b in bones}
    if (len(by_name) != len(bones) or set(by_name) != DEFORM | {"root"}
            or any(b.parent != PARENTS[b.name] or b.deform != (b.name != "root") for b in bones)):
        raise ValueError("Require the exact eighteen native joints and hierarchy.")
    for row in weights:
        if (not isinstance(row,dict) or not row or not set(row) <= DEFORM | {"root"}
                or any(type(v) not in (int,float) or not math.isfinite(v) or v < 0 for v in row.values())
                or sum(v > 0 for v in row.values()) > 4 or row.get("root",0) > 0
                or not math.isclose(sum(row.values()),1.,abs_tol=1e-6)):
            raise ValueError("Invalid existing native skin; no distal edit was planned.")
    keys,members,distances,counts = _surface_distances(points,faces,roles,bounds.height)
    previous_by_key = {}
    for key,row in zip(keys,weights):
        previous = previous_by_key.setdefault(key,row)
        if any(abs(previous.get(n,0)-row.get(n,0)) > 1e-6 for n in previous.keys() | row.keys()):
            raise ValueError("Contradictory coincident source weights cannot be silently repaired.")
    result,changed = [],0
    removed_by_role = {r:0. for r in CHAINS}
    for key,row in zip(keys,weights):
        if "body-core" in members[key]:
            result.append(dict(row)); continue
        role = next(iter(members[key]))
        allowed = set(CHAINS[role])
        foreign = sum(v for n,v in row.items() if n not in allowed)
        distance = distances[role][key]
        if foreign <= 1e-8 or distance <= collar_in_heights:
            result.append(dict(row)); continue
        mass = sum(v for n,v in row.items() if n in allowed)
        if mass <= 1e-6:
            raise ValueError("A distal authored limb has no existing same-chain skin authority.")
        fade = _smooth(collar_in_heights,2*collar_in_heights,distance)
        target = {n:v/mass for n,v in row.items() if n in allowed and v > 0}
        new = _bounded({n:row.get(n,0)*(1-fade)+target.get(n,0)*fade for n in row.keys() | target.keys()})
        result.append(new)
        changed += new != row
        removed_by_role[role] += foreign-sum(v for n,v in new.items() if n not in allowed)
    if not changed:
        raise ValueError("No positive distal foreign influence requires this edit.")
    return result,{"algorithm":ALGORITHM,"preceding_collar_in_heights":collar_in_heights,
        "fully_isolated_distance_in_heights":2*collar_in_heights,"changed_vertex_count":changed,
        "interface_vertex_counts":counts,"removed_foreign_mass_by_role":removed_by_role,
        "native_chains":{r:list(c) for r,c in CHAINS.items()},
        "distance_policy":"original polygon-edge geodesics; observation-only seam weld",
        "body_interfaces_and_chain_only_rows_exact":True,"native_rest_joints_unchanged":True,
        "scope":"Explicit existing-chain limb skin cleanup; not anatomy, contact or consumer acceptance."}
