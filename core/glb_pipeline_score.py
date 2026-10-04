"""Deterministic product score for the complete GLB-first character path."""

from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass
from typing import Any

from .export_contracts import ExportOutput
from .geometry_contracts import GeometrySurfaceOutput
from .glb_input_contracts import GLBFileInputOutput
from .motion_contracts import MotionOutput
from .pipeline_contracts import PipelineContext, PipelineStage
from .rig_contracts import RigOutput


@dataclass(frozen=True)
class GLBScoreComponent:
    name: str
    score: float
    weight: float
    available: bool = True
    evidence: str = ""
    applicable: bool = True

    def __post_init__(self) -> None:
        score = float(self.score)
        weight = float(self.weight)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("GLB score component must be inside [0, 1].")
        if not math.isfinite(weight) or weight <= 0.0:
            raise ValueError("GLB score component weight must be positive.")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "weight", weight)


@dataclass(frozen=True)
class GLBPipelineScore:
    score: float
    coverage: float
    components: tuple[GLBScoreComponent, ...]
    export_fidelity_score: float | None = None
    degraded: bool = False
    losses: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "coverage": self.coverage,
            "score_kind": "pipeline-completeness",
            "export_fidelity_score": self.export_fidelity_score,
            "degraded": self.degraded,
            "losses": self.losses,
            "components": {
                component.name: {
                    "score": component.score,
                    "weight": component.weight,
                    "available": component.available,
                    "evidence": component.evidence,
                    "applicable": component.applicable,
                }
                for component in self.components
            },
        }


def _ratio(numerator: Any, denominator: Any) -> float:
    try:
        top = float(numerator)
        bottom = float(denominator)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(top) or not math.isfinite(bottom) or bottom <= 0.0:
        return 0.0
    return min(max(top / bottom, 0.0), 1.0)


def _geometry_score(output: Any) -> tuple[float, str]:
    if not isinstance(output, GeometrySurfaceOutput):
        return 0.0, "missing GeometrySurfaceOutput"
    metrics = output.metrics
    vertex_ratio = _ratio(metrics.get("vertex_count"), metrics.get("source_vertex_count"))
    polygon_ratio = _ratio(metrics.get("polygon_count"), metrics.get("source_polygon_count"))
    score = min(vertex_ratio, polygon_ratio)
    return score, f"vertex={vertex_ratio:.3f}, polygon={polygon_ratio:.3f}"


def _optional_unit_score(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) and 0.0 <= score <= 1.0 else None


def _compatibility_scores(
    context: PipelineContext,
    geometry: Any,
) -> tuple[float | None, float | None, str]:
    structural = _optional_unit_score(
        context.metadata.get("glb_rig_structural_score")
    )
    semantic = _optional_unit_score(context.metadata.get("glb_rig_semantic_score"))
    archetype = context.metadata.get("glb_source_rig_archetype")
    compatible = context.metadata.get("glb_target_rig_compatible")
    if isinstance(geometry, GeometrySurfaceOutput):
        report = geometry.metadata.get("source_rig_compatibility", {})
        if isinstance(report, dict):
            if structural is None:
                structural = _optional_unit_score(report.get("structural_score"))
            if semantic is None:
                semantic = _optional_unit_score(report.get("semantic_score"))
            archetype = archetype or report.get("source_archetype")
            if compatible is None:
                compatible = report.get("target_compatible")
    return structural, semantic, (
        f"archetype={archetype or 'unknown'}, target_compatible={compatible}"
    )


def _rig_score(output: Any) -> tuple[float, str]:
    if not isinstance(output, RigOutput):
        return 0.0, "missing RigOutput"
    bone_score = _ratio(len(output.semantic_bones), 18)
    influence_count = output.metrics.get("max_influences_per_vertex")
    influence_score = (
        1.0
        if isinstance(influence_count, int)
        and not isinstance(influence_count, bool)
        and 1 <= influence_count <= 4
        else 0.0
    )
    score = 0.75 * bone_score + 0.25 * influence_score
    return score, f"semantic_bones={len(output.semantic_bones)}, max_influences={influence_count}"


def _motion_score(output: Any) -> tuple[float, str]:
    if not isinstance(output, MotionOutput):
        return 0.0, "missing MotionOutput"
    role_score = _ratio(len(output.source_bone_map), 17)
    clip_score = 1.0 if output.clips else 0.0
    sample_count = output.metrics.get(
        "pose_samples", output.metrics.get("baked_pose_samples", 0)
    )
    sample_score = 1.0 if _ratio(sample_count, 1) > 0 else 0.0
    score = 0.6 * role_score + 0.2 * clip_score + 0.2 * sample_score
    return score, f"roles={len(output.source_bone_map)}, clips={len(output.clips)}"


def _export_score(output: Any) -> tuple[float, str]:
    if not isinstance(output, ExportOutput):
        return 0.0, "missing ExportOutput"
    file_score = 0.0
    if output.path.is_file() and output.size_bytes > 0:
        digest = hashlib.sha256()
        actual_size = 0
        with output.path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                actual_size += len(chunk)
                digest.update(chunk)
        if actual_size == output.size_bytes and digest.hexdigest() == output.sha256:
            file_score = 1.0
    animation_score = 1.0
    if output.motion is not None:
        animation_score = _ratio(len(output.animation_names), len(output.motion.clips))
    return 0.7 * file_score + 0.3 * animation_score, (
        f"bytes={output.size_bytes}, animations={len(output.animation_names)}"
    )


def score_glb_first_pipeline(
    context: PipelineContext,
    *,
    image_score: float | None = None,
) -> GLBPipelineScore:
    input_output = context.get_output(PipelineStage.INPUT)
    input_score = 1.0 if isinstance(input_output, GLBFileInputOutput) else 0.0
    geometry_output = context.get_output(PipelineStage.GEOMETRY)
    geometry_score, geometry_evidence = _geometry_score(geometry_output)
    structure_score, compatibility_score, compatibility_evidence = (
        _compatibility_scores(context, geometry_output)
    )
    rig_score, rig_evidence = _rig_score(context.get_output(PipelineStage.RIG))
    motion_score, motion_evidence = _motion_score(context.get_output(PipelineStage.MOTION))
    export_score, export_evidence = _export_score(context.get_output(PipelineStage.EXPORT))
    route = context.metadata.get("glb_character_route")
    rig_applicable = route != "geometry-only"
    motion_applicable = rig_applicable and (
        not isinstance(input_output, GLBFileInputOutput) or input_output.animated
        or context.has_output(PipelineStage.MOTION)
    )

    if image_score is None:
        normalized_image_score = 0.0
        image_available = False
        image_evidence = "no image evidence; excluded from denominator"
    else:
        normalized_image_score = float(image_score)
        if not math.isfinite(normalized_image_score) or not 0.0 <= normalized_image_score <= 1.0:
            raise ValueError("image_score must be inside [0, 1] when provided.")
        image_available = True
        image_evidence = "provided image evidence"

    components = (
        GLBScoreComponent("input_integrity", input_score, 0.10, evidence="validated GLB contract"),
        GLBScoreComponent("geometry_preservation", geometry_score, 0.20, evidence=geometry_evidence),
        GLBScoreComponent(
            "rig_structure",
            structure_score or 0.0,
            0.05,
            available=rig_applicable and structure_score is not None,
            evidence=compatibility_evidence,
            applicable=rig_applicable,
        ),
        GLBScoreComponent(
            "rig_compatibility",
            compatibility_score or 0.0,
            0.10,
            available=rig_applicable and compatibility_score is not None,
            evidence=compatibility_evidence,
            applicable=rig_applicable,
        ),
        GLBScoreComponent("rig", rig_score, 0.15, available=rig_applicable,
                          evidence=rig_evidence, applicable=rig_applicable),
        GLBScoreComponent("motion", motion_score, 0.15, available=motion_applicable,
                          evidence=motion_evidence, applicable=motion_applicable),
        GLBScoreComponent("export", export_score, 0.15, evidence=export_evidence),
        GLBScoreComponent(
            "image", normalized_image_score, 0.10,
            available=image_available, evidence=image_evidence,
        ),
    )
    available_weight = sum(component.weight for component in components if component.available)
    weighted = sum(
        component.score * component.weight
        for component in components
        if component.available
    )
    total_weight = sum(component.weight for component in components if component.applicable)
    fidelity = context.metadata.get("glb_export_roundtrip")
    exported = context.get_output(PipelineStage.EXPORT)
    fidelity_score = None
    if (isinstance(fidelity, dict) and isinstance(exported, ExportOutput)
            and fidelity.get("sha256") == exported.sha256
            and isinstance(fidelity.get("passed"), bool)
            and isinstance(fidelity.get("sample_count"), int)
            and not isinstance(fidelity.get("sample_count"), bool)
            and fidelity["sample_count"] > 0 and export_score == 1.0):
        fidelity_score = 100.0 if fidelity["passed"] else 0.0
    losses = tuple(context.metadata.get("glb_route_losses", ()))
    return GLBPipelineScore(
        score=100.0 * weighted / available_weight,
        coverage=available_weight / total_weight,
        components=components,
        export_fidelity_score=fidelity_score,
        degraded=bool(losses),
        losses=losses,
    )


__all__ = (
    "GLBPipelineScore",
    "GLBScoreComponent",
    "score_glb_first_pipeline",
)
