from __future__ import annotations

import tempfile
import unittest
import hashlib
from pathlib import Path

from core.export_contracts import ExportOutput
from core.geometry_contracts import GeometryProjectionSpace, GeometrySurfaceOutput
from core.glb_input_contracts import GLBFileInputOutput
from core.glb_pipeline_score import score_glb_first_pipeline
from core.motion_contracts import MotionClipOutput, MotionOutput
from core.pipeline_contracts import PipelineContext, PipelineStage
from core.rig_contracts import RigOutput


class _Object:
    def __init__(self, name: str) -> None:
        self.name = name


def _input() -> GLBFileInputOutput:
    return GLBFileInputOutput(
        path="source.glb",
        implementation_id="glb-file-v1",
        size_bytes=100,
        sha256="b" * 64,
        node_names=("Character",),
        animation_names=("Walk",),
        scene_count=1,
        mesh_count=1,
        skin_count=1,
        material_count=1,
    )


def _complete_context(export_path: Path) -> PipelineContext:
    source = _input()
    mesh = _Object("Mesh")
    geometry = GeometrySurfaceOutput(
        blender_object=mesh,
        source=source,
        projection_space=GeometryProjectionSpace(32, 32, 64),
        implementation_id="glb-normalized-geometry-v1",
        metrics={
            "source_vertex_count": 100,
            "source_polygon_count": 50,
            "vertex_count": 100,
            "polygon_count": 50,
        },
    )
    armature = _Object("Rig")
    roles = {"root": "root", **{f"role-{index}": f"bone-{index}" for index in range(17)}}
    rig = RigOutput(
        geometry=geometry,
        blender_object=mesh,
        armature_object=armature,
        implementation_id="canonical-biped-v1",
        semantic_bones=roles,
        binding_method="canonical-distance",
        metrics={"max_influences_per_vertex": 4},
    )
    animated_roles = tuple(f"role-{index}" for index in range(17))
    clip = MotionClipOutput(
        name="Walk",
        action=object(),
        frame_start=1,
        frame_end=25,
        fps=24,
        animated_roles=animated_roles,
    )
    motion = MotionOutput(
        rig=rig,
        armature_object=armature,
        implementation_id="canonical-motion-retarget-v1",
        clips=(clip,),
        source_bone_map={role: f"source-{index}" for index, role in enumerate(animated_roles)},
        metrics={"baked_pose_samples": 25},
    )
    exported = ExportOutput(
        geometry=geometry,
        rig=rig,
        motion=motion,
        implementation_id="glb-export-v1",
        path=export_path,
        format="GLB",
        size_bytes=export_path.stat().st_size,
        sha256=hashlib.sha256(export_path.read_bytes()).hexdigest(),
        object_names=(mesh.name, armature.name),
        animation_names=("Walk",),
    )
    context = PipelineContext()
    for stage, output in (
        (PipelineStage.INPUT, source),
        (PipelineStage.GEOMETRY, geometry),
        (PipelineStage.RIG, rig),
        (PipelineStage.MOTION, motion),
        (PipelineStage.EXPORT, exported),
    ):
        context.set_output(stage, output)
    return context


class GLBPipelineScoreTests(unittest.TestCase):
    def test_complete_pipeline_scores_without_image_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character.glb"
            path.write_bytes(b"artifact")
            score = score_glb_first_pipeline(_complete_context(path))
        self.assertAlmostEqual(score.score, 100.0)
        self.assertAlmostEqual(score.coverage, 0.9)
        self.assertFalse(score.components[-1].available)

    def test_blank_image_penalizes_but_does_not_erase_pipeline_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "character.glb"
            path.write_bytes(b"artifact")
            score = score_glb_first_pipeline(_complete_context(path), image_score=0.0)
        self.assertAlmostEqual(score.score, 90.0)
        self.assertAlmostEqual(score.coverage, 1.0)

    def test_partial_pipeline_still_returns_a_score(self) -> None:
        source = _input()
        mesh = _Object("Mesh")
        geometry = GeometrySurfaceOutput(
            blender_object=mesh,
            source=source,
            projection_space=GeometryProjectionSpace(1, 1, 1),
            implementation_id="glb-normalized-geometry-v1",
            metrics={
                "source_vertex_count": 1,
                "source_polygon_count": 1,
                "vertex_count": 1,
                "polygon_count": 1,
            },
        )
        context = PipelineContext(outputs={
            PipelineStage.INPUT: source,
            PipelineStage.GEOMETRY: geometry,
        })
        score = score_glb_first_pipeline(context)
        self.assertGreater(score.score, 0.0)
        self.assertLess(score.score, 100.0)


if __name__ == "__main__":
    unittest.main()
