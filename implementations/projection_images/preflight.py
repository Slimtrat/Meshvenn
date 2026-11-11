"""Explicit, reproducible accepted-alignment bindings for the existing INPUT.

This module has no Blender dependency. Put a PreflightProjectionRequest in
PipelineContext.source to opt in; unbound scene projections retain their manual
preparation path. Bound pixels come from the preserved diagnostic sources.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence

from ...core.diagnostic_contracts import DiagnosticReport, ViewRevision, ViewSetRevision
from ...core.diagnostics_preflight import (
    AlignmentAnchor, CertifiedProjectionInput, PreflightPolicy, PreflightResult,
    ViewInput, accept_alignment, analyze_preflight,
)
from ...core.projection_alignment import ProjectionAlignment


@dataclass(frozen=True)
class ProjectionAlignmentBinding:
    projection_name: str
    view_id: str
    proposal_id: str
    rgb_encoding: str

    def __post_init__(self):
        for name in ("projection_name", "view_id", "proposal_id"):
            value = getattr(self, name)
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"{name} must be explicit nonempty text.")
        if self.rgb_encoding not in ("scene-linear", "sRGB"):
            raise ValueError("A bound source must explicitly declare scene-linear or sRGB color.")


@dataclass(frozen=True)
class CertifiedProjectionBinding:
    binding: ProjectionAlignmentBinding
    revision: ViewRevision
    accepted: CertifiedProjectionInput
    report: DiagnosticReport

    @property
    def dependency_fingerprint(self) -> str:
        return self.report.dependency_fingerprint

    def metadata(self) -> dict[str, object]:
        accepted = self.accepted
        return {
            "view_id": self.revision.view_id,
            "view_revision": self.revision.revision,
            "proposal_id": self.binding.proposal_id,
            "dependency_fingerprint": self.dependency_fingerprint,
            "source_image_sha256": accepted.source_image_sha256,
            "source_mask_sha256": accepted.source_mask_sha256,
            "decoded_image_sha256": accepted.source.image.decoded_sha256,
            "decoded_mask_sha256": accepted.source.mask.decoded_sha256 if accepted.source.mask else None,
            "certificate_sha256": accepted.certificate_sha256,
            "color_transform_sha256": accepted.color_transform_sha256,
            "mask_transform_sha256": accepted.mask_transform_sha256,
            "rgb_encoding": self.binding.rgb_encoding,
        }


@dataclass(frozen=True)
class PreflightProjectionRequest:
    """Bind preserved originals, rather than scene image buffers, by explicit name.

    PNG adapter values use binding rgb_encoding='sRGB'. A trusted from_pixels
    host must declare its actual decoded encoding. Alpha is always straight.
    Scene alpha_threshold must equal policy.alpha_threshold; construct policy
    from the scene value to preserve its exact stored threshold.
    """
    result: PreflightResult
    view_set: ViewSetRevision
    inputs: Mapping[str, ViewInput]
    bindings: tuple[ProjectionAlignmentBinding, ...]
    anchors: tuple[AlignmentAnchor, ...] = ()
    policy: PreflightPolicy = field(default_factory=PreflightPolicy)

    def __post_init__(self):
        if (type(self.result) is not PreflightResult or type(self.view_set) is not ViewSetRevision
                or type(self.policy) is not PreflightPolicy):
            raise TypeError("Preflight request requires typed results, source revisions and policy.")
        copied = dict(self.inputs)
        if any(type(key) is not str or type(value) is not ViewInput for key, value in copied.items()):
            raise TypeError("Preflight inputs must map explicit view IDs to immutable ViewInput values.")
        object.__setattr__(self, "inputs", MappingProxyType(copied))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "anchors", tuple(self.anchors))
        if not self.bindings or any(type(b) is not ProjectionAlignmentBinding for b in self.bindings):
            raise TypeError("An explicit request needs at least one typed projection binding.")
        if any(type(a) is not AlignmentAnchor for a in self.anchors):
            raise TypeError("Alignment anchors must be typed.")
        for name in ("projection_name", "view_id", "proposal_id"):
            values = tuple(getattr(binding, name) for binding in self.bindings)
            if len(set(values)) != len(values):
                raise ValueError(f"Duplicate {name} in accepted projection bindings.")

    def projection_names(self, projections: Sequence) -> frozenset[str]:
        names = frozenset(binding.projection_name for binding in self.bindings)
        for name in names:
            matches = [p for p in projections if str(p.name).strip() == name]
            if len(matches) != 1 or not matches[0].enabled:
                raise ValueError(f'Bound projection "{name}" must name exactly one enabled scene projection.')
        return names

    def certify(self, projections: Sequence, *, alpha_threshold: float) -> Mapping[str, CertifiedProjectionBinding]:
        """Reproduce every proposal before constructing consumers or publishing state."""
        self.projection_names(projections)
        if alpha_threshold != self.policy.alpha_threshold:
            raise ValueError("Scene and preflight alpha thresholds differ; rerun preparation with the current policy.")
        views = {v.view_id: v for v in self.view_set.views}
        proposals = {p.proposal_id: p for p in self.result.proposals}
        reproduced = analyze_preflight(self.view_set, self.inputs, anchors=self.anchors, policy=self.policy)
        if reproduced.report.dependency_fingerprint != self.result.report.dependency_fingerprint:
            raise ValueError("Accepted preflight dependencies changed; analyze the current source revision.")
        certified = {}
        for binding in self.bindings:
            view = views.get(binding.view_id)
            proposal = proposals.get(binding.proposal_id)
            if view is None or proposal is None or proposal.view_id != binding.view_id:
                raise ValueError("Accepted binding refers to an unknown or mismatched view/proposal.")
            if proposal not in reproduced.proposals:
                raise ValueError("Accepted proposal cannot be reproduced from the current original sources.")
            projection = next(p for p in projections if str(p.name).strip() == binding.projection_name)
            camera = view.camera
            azimuth = math.degrees(float(projection.azimuth))
            elevation = math.degrees(float(projection.elevation))
            if (camera.azimuth_degrees is None or camera.elevation_degrees is None
                    or not math.isfinite(azimuth) or not math.isfinite(elevation)
                    or abs((azimuth-camera.azimuth_degrees+180) % 360-180) > 1e-4
                    or abs(elevation-camera.elevation_degrees) > 1e-4
                    or bool(projection.flip_x) != camera.flip_x):
                raise ValueError("Bound scene camera differs from its preflight view revision.")
            scene_alignment = ProjectionAlignment(
                float(getattr(projection, "alignment_offset_u", 0.0)),
                float(getattr(projection, "alignment_offset_v", 0.0)),
                float(getattr(projection, "alignment_scale", 1.0)))
            if scene_alignment != view.alignment:
                raise ValueError("Bound scene alignment differs from the unmodified source revision.")
            accepted = accept_alignment(proposal, reproduced, self.view_set, self.inputs,
                                        anchors=self.anchors, policy=self.policy)
            certified[binding.projection_name] = CertifiedProjectionBinding(
                binding, view, accepted, reproduced.report)
        return MappingProxyType(certified)
