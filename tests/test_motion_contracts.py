from __future__ import annotations

import unittest

from core.geometry_contracts import GeometryProjectionSpace, GeometrySurfaceOutput
from core.motion_contracts import (
    MotionClipOutput,
    MotionOutput,
    require_motion_output,
    validate_motion_clip_output,
    validate_motion_output,
)
from core.pipeline_contracts import PipelineContext, PipelineStage
from core.rig_contracts import RigOutput, require_rig_output, validate_rig_output


class MotionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = object()
        self.armature = object()
        geometry = GeometrySurfaceOutput(
            blender_object=self.mesh,
            source=object(),
            projection_space=GeometryProjectionSpace(8, 8, 16),
            implementation_id="test-geometry",
        )
        self.rig = RigOutput(
            geometry=geometry,
            blender_object=self.mesh,
            armature_object=self.armature,
            implementation_id="test-rig",
            semantic_bones={"upper_arm.L": "upper_arm.L"},
            binding_method="test-binding",
        )
        self.clip = MotionClipOutput(
            "Wave",
            object(),
            1,
            25,
            24,
            ("upper_arm.L", "upper_arm.L"),
            {"source": "fixture"},
        )

    def output(self, **overrides) -> MotionOutput:
        values = {
            "rig": self.rig,
            "armature_object": self.armature,
            "implementation_id": "test-motion",
            "clips": (self.clip,),
            "source_bone_map": {"upper_arm.L": "arm_joint_L_1"},
            "root_motion_mode": "in_place",
            "metrics": {"sampled_frames": 25},
        }
        values.update(overrides)
        return MotionOutput(**values)

    def test_clip_normalizes_timing_roles_and_metadata(self) -> None:
        self.assertEqual(self.clip.name, "Wave")
        self.assertEqual(self.clip.animated_roles, ("upper_arm.L",))
        self.assertEqual(self.clip.duration_seconds, 1.0)
        self.assertEqual(self.clip.metadata, {"source": "fixture"})
        self.assertIs(validate_motion_clip_output(self.clip), self.clip)

    def test_clip_rejects_invalid_action_timing_and_roles(self) -> None:
        with self.assertRaises(ValueError):
            MotionClipOutput("", object(), 1, 2, 24, ("upper_arm.L",))
        with self.assertRaises(ValueError):
            MotionClipOutput("Wave", None, 1, 2, 24, ("upper_arm.L",))
        with self.assertRaises(ValueError):
            MotionClipOutput("Wave", object(), 2, 1, 24, ("upper_arm.L",))
        with self.assertRaises(ValueError):
            MotionClipOutput("Wave", object(), 2, 2, 24, ("upper_arm.L",))
        with self.assertRaises(ValueError):
            MotionClipOutput("Wave", object(), 1, 2, 0, ("upper_arm.L",))
        with self.assertRaises(ValueError):
            MotionClipOutput("Wave", object(), 1, 2, 24, ())

    def test_output_preserves_rig_and_normalizes_metadata(self) -> None:
        output = self.output()
        self.assertIs(output.rig, self.rig)
        self.assertIs(output.armature_object, self.armature)
        self.assertEqual(output.root_motion_mode, "IN_PLACE")
        self.assertEqual(output.source_bone_map, {"upper_arm.L": "arm_joint_L_1"})
        self.assertEqual(output.metrics, {"sampled_frames": 25})
        self.assertIs(validate_motion_output(output), output)

    def test_output_rejects_incompatible_armature_clips_mapping_and_mode(self) -> None:
        with self.assertRaises(ValueError):
            self.output(armature_object=object())
        with self.assertRaises(ValueError):
            self.output(clips=())
        with self.assertRaises(ValueError):
            self.output(clips=(self.clip, self.clip))
        unknown_clip = MotionClipOutput("Tail", object(), 1, 2, 24, ("tail",))
        with self.assertRaises(ValueError):
            self.output(clips=(unknown_clip,), source_bone_map={"tail": "Tail"})

        with self.assertRaises(ValueError):
            self.output(source_bone_map={"spine": "torso_joint_2"})
        with self.assertRaises(ValueError):
            self.output(root_motion_mode="teleport")
        with self.assertRaises(ValueError):
            self.output(schema_version=2)

    def test_context_accessors_validate_stage_outputs(self) -> None:
        output = self.output()
        context = PipelineContext()
        context.set_output(PipelineStage.RIG, self.rig)
        context.set_output(PipelineStage.MOTION, output)
        self.assertIs(require_rig_output(context), self.rig)
        self.assertIs(validate_rig_output(self.rig), self.rig)
        self.assertIs(require_motion_output(context), output)
        context.set_output(PipelineStage.MOTION, object())
        with self.assertRaises(TypeError):
            require_motion_output(context)

    def test_validators_reject_untyped_values(self) -> None:
        with self.assertRaises(TypeError):
            validate_rig_output(object())
        with self.assertRaises(TypeError):
            validate_motion_clip_output(object())
        with self.assertRaises(TypeError):
            validate_motion_output(object())


if __name__ == "__main__":
    unittest.main()
