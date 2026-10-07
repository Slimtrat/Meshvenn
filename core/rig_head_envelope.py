"""Conservative, topology-backed head weight isolation for upright bipeds.

A closed central narrowing with wider sections both below and above is a
surface cue, not an anatomical joint detector. Missing or ambiguous evidence
leaves the existing solver unchanged. Rest joints are never moved here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .canonical_rig import MeshBounds
from .rig_lower_body import _sections_at, _triangles

ALGORITHM = "regional-fitted-v2-head-isolation"


@dataclass(frozen=True)
class HeadEnvelope:
    start_z: float
    end_z: float
    neck_z: float
    contrast: float
    section_count: int

    def __post_init__(self):
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (self.start_z, self.end_z, self.neck_z, self.contrast))
                or not self.start_z < self.neck_z < self.end_z
                or not .55 <= self.contrast <= 1
                or type(self.section_count) is not int or self.section_count < 5):
            raise ValueError("Invalid observed head isolation envelope.")

    def as_dict(self):
        return {"algorithm": "closed-central-neck-narrowing-v1", "start_z": self.start_z,
                "end_z": self.end_z, "neck_z": self.neck_z, "contrast": self.contrast,
                "closed_section_count": self.section_count,
                "scope": "Surface cue for skin weights only; native rest joints are unchanged."}


def observe_head_envelope(vertices, triangles, bounds: MeshBounds) -> HeadEnvelope | None:
    """Observe a neck constriction using height-normalized closed sections.

    Independent of surface vertex density, face order and UV seam duplication.
    Require persistent central rings and bilateral vertical contrast. A block,
    a tapered head, an open scan or two disconnected lobes cannot qualify.
    """
    if not isinstance(bounds, MeshBounds):
        raise TypeError("Head observation requires MeshBounds.")
    if not vertices or any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in vertices):
        raise ValueError("Head observation requires finite 3D vertices.")
    if triangles is None:
        return None
    origin = (bounds.center_x, bounds.center_y, bounds.minimum[2])
    points = [tuple((v-o)/bounds.height for v, o in zip(p, origin)) for p in vertices]
    faces = _triangles(points, triangles)
    # Weld coincident seam positions, then require one surface component that
    # actually connects torso to crown. Stacked disconnected props are not a
    # neck even if their projected horizontal envelopes happen to look like one.
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for _, _, face in faces:
        keys = [tuple(round(v, 6) for v in point) for point in face]
        for key in keys[1:]:
            a, b = find(keys[0]), find(key)
            if a != b:
                parent[max(a, b)] = min(a, b)
    extents = {}
    for key in parent:
        component = find(key)
        low, high = extents.get(component, (key[2], key[2]))
        extents[component] = (min(low, key[2]), max(high, key[2]))
    eligible = {key for key, (low, high) in extents.items() if low <= .55 and high >= .95}
    if len(eligible) != 1:
        return None
    component = next(iter(eligible))
    faces = [face for face in faces if find(tuple(round(v, 6) for v in face[2][0])) == component]
    sections = {}
    for index in range(120, 188):
        z = index*.005
        rings = [(low, high, section) for low, high, section in _sections_at(faces, z)
                 if low < -.005 and high > .005 and high-low <= .45 and abs(section.x) <= .03]
        if len(rings) == 1:
            low, high, section = rings[0]
            sections[index] = (section, high-low)
    candidates = []
    for index, (section, width) in sections.items():
        if not .64 <= section.z <= .88 or width > .16:
            continue
        before = [s.area_proxy for i, (s, _) in sections.items() if 5 <= index-i <= 13]
        after = [s.area_proxy for i, (s, _) in sections.items() if 5 <= i-index <= 18]
        if min(len(before), len(after)) < 4:
            continue
        contrast = 1-section.area_proxy/min(max(before), max(after))
        # A single thin/noisy slice is not a neck. Missing slices break the
        # persistence proof; no interpolation of unobserved surface rings.
        run = [index]
        for direction in (-1, 1):
            i = index+direction
            while i in sections and sections[i][0].area_proxy <= 1.5*section.area_proxy:
                run.append(i)
                i += direction
        if contrast >= .55 and len(run) >= 5 and max(run)-min(run) <= 14:
            candidates.append((contrast, section, run))
    if not candidates:
        return None
    contrast, neck, run = max(candidates, key=lambda item: (item[0], -item[1].z))
    # This is an upright A/T-pose prior. Do not relabel raised arms or tall
    # lateral attachments as head merely because they exceed the neck height.
    if any(p[2] > max(run)*.005+.04 and abs(p[0]) > .23 for p in points):
        return None
    # Fade across the observed neck, ending before the expanded head shell.
    start = min(run)*.005-.005
    end = max(run)*.005+.010
    return HeadEnvelope(origin[2]+start*bounds.height, origin[2]+end*bounds.height,
                        origin[2]+neck.z*bounds.height, contrast, len(run))


def isolate_head_weights(weights: Mapping[str, float], z: float, envelope: HeadEnvelope | None,
                         *, max_influences=4) -> dict[str, float]:
    """Transfer influence to head smoothly; never perturb vertices below neck.

    Convex mass transfer, deterministic four-influence pruning and normalization.
    The cranial shell becomes rigid to its existing head joint, including when
    its wide corners are closer to arm bones than to the axial centerline.
    """
    if (not math.isfinite(z) or type(max_influences) is not int or max_influences < 1
            or not weights or len(weights) > max_influences
            or any(not isinstance(name, str) or not name or not math.isfinite(value) or value <= 0
                   for name, value in weights.items())
            or not math.isclose(sum(weights.values()), 1, abs_tol=1e-6)):
        raise ValueError("Expected finite normalized bounded skin weights and position.")
    if envelope is not None and not isinstance(envelope, HeadEnvelope):
        raise TypeError("Expected a HeadEnvelope or explicit missing evidence.")
    if envelope is None or z <= envelope.start_z:
        return dict(weights)
    if z >= envelope.end_z:
        return {"head": 1.0}
    t = (z-envelope.start_z)/(envelope.end_z-envelope.start_z)
    blend = t*t*(3-2*t)
    values = {name: value*(1-blend) for name, value in weights.items()}
    values["head"] = values.get("head", 0)+blend
    # Blender's GLB exporter removes influences <= 1e-4. Remove them in the
    # selected source FIRST, with a float32 safety margin, so ordinary strict
    # weight fidelity remains valid; never relax its 1e-4 transport gate.
    kept = sorted(((name, value) for name, value in values.items() if value > 1.01e-4),
                  key=lambda item: (-item[1], item[0]))[:max_influences]
    total = sum(value for _, value in kept)
    return {name: value/total for name, value in kept}
