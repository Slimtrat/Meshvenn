"""Local arm-chain weights; no engine or Blender dependency."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Segment:
    head: tuple[float, float, float]
    tail: tuple[float, float, float]

    def __post_init__(self):
        if (
            len(self.head) != 3
            or len(self.tail) != 3
            or any(not math.isfinite(v) for v in (*self.head, *self.tail))
            or math.dist(self.head, self.tail) <= 1e-12
        ):
            raise ValueError("Require a finite nondegenerate native segment")


def smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def longitudinal(point, segments):
    candidates = []
    offset = 0.0
    for segment in segments:
        axis = tuple(b - a for a, b in zip(segment.head, segment.tail))
        length = math.sqrt(sum(v * v for v in axis))
        if length <= 1e-12:
            raise ValueError("Degenerate native arm segment")
        t = max(
            0.0,
            min(
                1.0,
                sum((p - a) * v for p, a, v in zip(point, segment.head, axis))
                / (length * length),
            ),
        )
        distance = math.dist(
            point, tuple(a + t * v for a, v in zip(segment.head, axis))
        )
        candidates.append((distance, offset + t * length))
        offset += length
    return min(candidates)[1]


def bounded(row):
    kept = sorted(
        ((n, v) for n, v in row.items() if v > 1.01e-4), key=lambda x: (-x[1], x[0])
    )[:4]
    total = sum(v for _, v in kept)
    if not total:
        raise ValueError("Empty skin row")
    return {n: v / total for n, v in kept}


def localize_arms(
    points,
    weights,
    bones,
    *,
    blend_fraction=0.18,
    radial_expansion=0.0,
    bend_axis=(0.0, 1.0, 0.0),
):
    if not 0.08 <= blend_fraction <= 0.35:
        raise ValueError("Arm blend fraction must be in [.08,.35]")
    if not math.isfinite(radial_expansion) or not 0.0 <= radial_expansion <= 3.0:
        raise ValueError("Invalid radial expansion")
    if len(points) != len(weights) or not points:
        raise ValueError("Require matching source points and skin")
    chains = {
        side: tuple(f"{part}.{side}" for part in ("upper_arm", "forearm", "hand"))
        for side in ("L", "R")
    }
    segments = {side: [bones[n] for n in names] for side, names in chains.items()}
    lengths = {
        side: [math.dist(b.head, b.tail) for b in s] for side, s in segments.items()
    }
    radii = {}
    for side, names in chains.items():
        joint = segments[side][1].head
        axis = tuple(b - a for a, b in zip(joint, segments[side][1].tail))
        length = lengths[side][1]
        axis = tuple(v / length for v in axis)
        perpendicular = (
            axis[1] * bend_axis[2] - axis[2] * bend_axis[1],
            axis[2] * bend_axis[0] - axis[0] * bend_axis[2],
            axis[0] * bend_axis[1] - axis[1] * bend_axis[0],
        )
        norm = math.sqrt(sum(v * v for v in perpendicular))
        if norm < 1e-8:
            raise ValueError("Unobserved flexion plane")
        perpendicular = tuple(v / norm for v in perpendicular)
        values = []
        for p, row in zip(points, weights):
            if sum(row.get(n, 0.0) for n in names) <= 0.6:
                continue
            along = sum((v - j) * a for v, j, a in zip(p, joint, axis))
            if abs(along) < 0.12 * min(lengths[side][:2]):
                values.append(
                    abs(sum((v - j) * a for v, j, a in zip(p, joint, perpendicular)))
                )
        if len(values) < 4 and radial_expansion:
            raise ValueError("Insufficient observed elbow collar support")
        values.sort()
        radii[side] = values[int(0.95 * (len(values) - 1))] if values else None
    changed = {side: 0 for side in chains}
    result = []
    for point, old in zip(points, weights):
        if len(point) != 3 or any(not math.isfinite(v) for v in point):
            raise ValueError("Nonfinite point")
        if (
            not old
            or any(not math.isfinite(v) or v <= 0 for v in old.values())
            or not math.isclose(sum(old.values()), 1.0, abs_tol=1e-6)
            or len(old) > 4
        ):
            raise ValueError("Require bounded normalized native weights")
        new = dict(old)
        for side in chains:
            mass = sum(new.get(n, 0.0) for n in chains[side])
            if mass == 0.0:
                continue
            s = longitudinal(point, segments[side])
            upper, forearm, hand = lengths[side]
            # Preserve the arm-chain total at ambiguous torso attachments.
            # Its child joints must not pull those proximal vertices at all.
            root = smooth(0.10 * upper, 0.25 * upper, s) if mass > 0.5 else 0.0
            elbow_half = max(
                blend_fraction * min(upper, forearm),
                radial_expansion * (radii[side] or 0.0),
            )
            wrist_half = blend_fraction * min(forearm, hand)
            if elbow_half > min(0.85 * upper, forearm - wrist_half - 0.02 * forearm):
                raise ValueError(
                    "Elbow collar overlaps adjacent joints; source geometry needs regeneration"
                )
            elbow = smooth(upper - elbow_half, upper + elbow_half, s)
            wrist = smooth(
                upper + forearm - wrist_half, upper + forearm + wrist_half, s
            )
            a, b, c = chains[side]
            target = {a: 1.0 - elbow, b: elbow * (1.0 - wrist), c: wrist}
            for n in chains[side]:
                new.pop(n, None)
            for n in new:
                new[n] *= 1.0 - root
            chain_mass = mass + (1.0 - mass) * root
            new.update({n: v * chain_mass for n, v in target.items() if v > 0})
        final = bounded(new) if new != old else dict(old)
        for side in chains:
            changed[side] += any(
                abs(final.get(n, 0) - old.get(n, 0)) > 1e-8 for n in chains[side]
            )
        result.append(final)
    return result, dict(
        algorithm="longitudinal-local-arm-chains-v2",
        blend_fraction=blend_fraction,
        radial_expansion=radial_expansion,
        observed_elbow_radius=radii,
        changed_vertices=changed,
        scope="Existing canonical arm chains; rest mesh, UVs and native joints unchanged",
    )
