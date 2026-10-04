"""Topology-backed lower-body observations, with explicit canonical fallbacks.

Horizontal surface sections locate separated legs and ankle/knee cues. Hip
height is an equal-link-length *prior* anchored to those observations, not an
anatomical joint detector. A missing or ambiguous cue never becomes a claim of
measurement. Coordinates and tolerances are normalized by model height.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .canonical_rig import MeshBounds

Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class LegObservation:
    hip: Point3 | None = None
    knee: Point3 | None = None
    ankle: Point3 | None = None
    toe_y: float | None = None


@dataclass(frozen=True)
class LowerBodyFit:
    left: LegObservation
    right: LegObservation
    evidence: dict[str, object]


@dataclass(frozen=True)
class _Section:
    z: float
    x: float
    y: float
    area_proxy: float
    front: float


def _triangles(vertices, triangles):
    result = []
    for indices in triangles:
        indices = tuple(indices)
        if len(indices) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in indices):
            raise ValueError("Lower-body triangles require three valid integer vertex indices.")
        if len(set(indices)) != 3:
            raise ValueError("Lower-body triangles must have distinct indices.")
        face = tuple(vertices[i] for i in indices)
        result.append((min(p[2] for p in face), max(p[2] for p in face), face))
    return result


def _sections_at(triangles, z):
    segments = {}
    for low, high, face in triangles:
        if not low < z <= high:
            continue
        hits = []
        for a, b in zip(face, (*face[1:], face[0])):
            if a[2] < z <= b[2] or b[2] < z <= a[2]:
                t = (z - a[2]) / (b[2] - a[2])
                hits.append(tuple(a[i] + t * (b[i] - a[i]) for i in (0, 1)))
        if len(hits) != 2:
            continue
        keys = [tuple(round(v, 6) for v in hit) for hit in hits]
        if keys[0] != keys[1]:
            key = tuple(sorted(keys))
            ordered = sorted(hits)
            segments[key] = min(segments.get(key, ordered), ordered)

    # Union of projected segment intervals is independent of vertex density,
    # triangulation and UV seams. Detached hands/accessories are not leg rings.
    groups = []
    for keys, hits in sorted(segments.items(), key=lambda item: min(p[0] for p in item[1])):
        low = min(p[0] for p in hits)
        high = max(p[0] for p in hits)
        if groups and low <= groups[-1][0] + 1e-6:
            groups[-1][0] = max(groups[-1][0], high)
            groups[-1][1].append((keys, hits))
        else:
            groups.append([high, [(keys, hits)]])
    rings = []
    for _, group in groups:
        degrees = {}
        for keys, _ in group:
            for key in keys:
                degrees[key] = degrees.get(key, 0) + 1
        if len(degrees) < 3 or any(count != 2 for count in degrees.values()):
            continue
        points = [point for _, hits in group for point in hits]
        x_low, x_high = min(p[0] for p in points), max(p[0] for p in points)
        y_low, y_high = min(p[1] for p in points), max(p[1] for p in points)
        if (x_high - x_low) * (y_high - y_low) <= 1e-8:
            continue
        rings.append((x_low, x_high, _Section(z, (x_low + x_high) / 2,
                                             (y_low + y_high) / 2,
                                             (x_high - x_low) * (y_high - y_low), y_low)))
    return rings


def _line_error(sections):
    origin = sum(s.z for s in sections) / len(sections)
    denominator = sum((s.z - origin) ** 2 for s in sections)
    error = 0.0
    slopes = []
    for axis in ("x", "y"):
        center = sum(getattr(s, axis) for s in sections) / len(sections)
        slope = sum((s.z - origin) * (getattr(s, axis) - center) for s in sections) / denominator
        error += sum((getattr(s, axis) - center - slope * (s.z - origin)) ** 2 for s in sections)
        slopes.append(slope)
    return error, slopes


def _knee(sections, ankle_z, crotch):
    track = [s for s in sections if ankle_z + .025 <= s.z <= crotch - .015]
    lower = ankle_z + .32 * (crotch + .05 - ankle_z)
    upper = ankle_z + .65 * (crotch + .05 - ankle_z)
    candidates = [s for s in track if lower <= s.z <= upper]
    if len(track) < 12 or not candidates:
        return None, "insufficient-sections", 0.0
    # A knee narrowing must have a wider calf AND thigh, not just a tapered leg.
    valleys = []
    for section in candidates:
        before = [s.area_proxy for s in track if .025 <= section.z - s.z <= .075]
        after = [s.area_proxy for s in track if .025 <= s.z - section.z <= .075]
        if before and after:
            contrast = 1 - section.area_proxy / min(max(before), max(after))
            valleys.append((contrast, section))
    if valleys:
        contrast, section = max(valleys, key=lambda item: (item[0], -item[1].z))
        if contrast >= .15:
            return section, "calf-thigh-section-narrowing", contrast
    baseline, _ = _line_error(track)
    if baseline < 1e-8:
        return None, "no-knee-cue", 0.0
    breaks = []
    for section in candidates:
        before = [s for s in track if s.z <= section.z]
        after = [s for s in track if s.z >= section.z]
        if min(len(before), len(after)) < 5:
            continue
        first, slope_first = _line_error(before)
        second, slope_second = _line_error(after)
        bend = math.dist(slope_first, slope_second)
        breaks.append((first + second, section, bend))
    if breaks:
        error, section, bend = min(breaks, key=lambda item: (item[0], item[1].z))
        improvement = max(0.0, 1 - error / baseline)
        if improvement >= .70 and bend >= .10:
            return section, "centerline-bend", improvement
    return None, "ambiguous-knee-cue", 0.0


def _center_at(sections, z):
    ordered = sorted(sections, key=lambda s: abs(s.z - z))[:2]
    a, b = ordered
    t = (z - a.z) / (b.z - a.z)
    return (a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), z)


def fit_lower_body(vertices: Sequence[Point3], triangles: Iterable[Sequence[int]] | None,
                   bounds: MeshBounds) -> LowerBodyFit:
    if not isinstance(bounds, MeshBounds):
        raise TypeError("Lower-body fitting requires MeshBounds.")
    if not vertices or any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in vertices):
        raise ValueError("Lower-body vertices require three finite coordinates.")
    evidence = {"algorithm": "closed-horizontal-sections-v1", "hip_policy":
                "0.95 femur-to-tibia length prior; not inferred anatomy", "legs": {}}
    if triangles is None:
        evidence["fallback_reason"] = "triangle-topology-unavailable"
        return LowerBodyFit(LegObservation(), LegObservation(), evidence)
    origin = (bounds.center_x, bounds.center_y, bounds.minimum[2])
    points = [tuple((v - o) / bounds.height for v, o in zip(p, origin)) for p in vertices]
    faces = _triangles(points, triangles)
    tracks = {"L": [], "R": []}
    merged = []
    for index in range(1, 115):
        z = .005 * index
        rings = _sections_at(faces, z)
        merged.append((z, any(low <= -.025 and high >= .025 for low, high, _ in rings)))
        for side, sign in (("L", 1), ("R", -1)):
            candidates = [section for low, high, section in rings
                          if (low > .003 if sign == 1 else high < -.003)
                          and max(abs(low), abs(high)) < .18 and high - low >= .012]
            if candidates:
                tracks[side].append(min(candidates, key=lambda s: abs(s.x)))
    crotch = next((z for index, (z, joined) in enumerate(merged[:-3])
                   if z >= .30 and joined and all(flag for _, flag in merged[index:index + 4])
                   and all(sum(s.z < z for s in track) >= 20 for track in tracks.values())), None)
    evidence["crotch_height_in_heights"] = crotch
    observations = {}

    def world(point):
        return tuple(v * bounds.height + o for v, o in zip(point, origin))

    for side, sections in tracks.items():
        report = {"closed_section_count": len(sections), "ankle_method": "canonical-prior",
                  "knee_method": "canonical-prior", "hip_method": "canonical-prior"}
        evidence["legs"][side] = report
        low = [s for s in sections if .02 <= s.z <= .14]
        foot = [s.area_proxy for s in sections if s.z <= .03]
        if len(low) < 12 or not foot or crotch is None:
            report["fallback_reason"] = "insufficient-separated-leg-or-foot-evidence"
            observations[side] = LegObservation()
            continue
        smallest = min(s.area_proxy for s in low)
        contrast = 1 - smallest / max(foot)
        if contrast < .20:
            report["fallback_reason"] = "no-ankle-narrowing"
            observations[side] = LegObservation()
            continue
        ankle = next(s for s in low if s.area_proxy <= smallest * 1.05)
        usable = [s for s in sections if s.z < crotch]
        knee, method, confidence = _knee(usable, ankle.z, crotch)
        report.update(ankle_method="foot-to-leg-narrowing", ankle_height_in_heights=ankle.z,
                      ankle_contrast=contrast, knee_method=method, knee_evidence=confidence)
        toe = min(s.front for s in sections if s.z < ankle.z)
        if knee is None:
            report["fallback_reason"] = method
            observations[side] = LegObservation(ankle=world((ankle.x, ankle.y, ankle.z)),
                                                 toe_y=toe * bounds.height + origin[1])
            continue
        hip_z = knee.z + .95 * (knee.z - ankle.z)
        report["knee_height_in_heights"] = knee.z
        if not .35 <= hip_z <= .56 or not -.04 <= hip_z - crotch <= .12:
            report["fallback_reason"] = "hip-length-prior-inconsistent-with-surface"
            hip = None
        else:
            center = _center_at(usable, hip_z)
            sign = 1 if side == "L" else -1
            if not .01 < sign * center[0] < .15 or abs(center[1]) > bounds.depth / (2 * bounds.height):
                report["fallback_reason"] = "hip-center-extrapolation-outside-body"
                hip = None
            else:
                hip = world(center)
                report.update(hip_method="observed-knee-ankle-length-prior", hip_height_in_heights=hip_z)
        observations[side] = LegObservation(hip, world((knee.x, knee.y, knee.z)),
                                             world((ankle.x, ankle.y, ankle.z)),
                                             toe * bounds.height + origin[1])
    hips = [observations[s].hip for s in ("L", "R")]
    reason = ("bilateral-hip-evidence-unavailable" if any(hip is None for hip in hips) else
              "inconsistent-bilateral-hip-heights" if abs(hips[0][2] - hips[1][2]) > .035 * bounds.height else None)
    if reason:
        for side, leg in observations.items():
            if leg.hip is not None:
                observations[side] = LegObservation(None, leg.knee, leg.ankle, leg.toe_y)
                evidence["legs"][side].update(hip_method="canonical-prior", fallback_reason=reason)
                evidence["legs"][side].pop("hip_height_in_heights", None)
    return LowerBodyFit(observations["L"], observations["R"], evidence)
