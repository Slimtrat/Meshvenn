from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from core.export_contracts import ExportOutput, require_export_output, validate_export_output
from core.geometry_contracts import GeometryProjectionSpace, GeometrySurfaceOutput
from core.motion_contracts import MotionClipOutput, MotionOutput
from core.pipeline_contracts import PipelineContext, PipelineStage
from core.rig_contracts import RigOutput


class ExportContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = SimpleNamespace(name="Character")
        self.armature = SimpleNamespace(name="Armature")
        self.geometry = GeometrySurfaceOutput(
            blender_object=self.mesh,
            source=object(),
            projection_space=GeometryProjectionSpace(8, 8, 16),
            implementation_id="test-geometry",
        )
        self.rig = RigOutput(
            geometry=self.geometry,
            blender_object=self.mesh,
            armature_object=self.armature,
            implementation_id="test-rig",
            semantic_bones={"upper_arm.L": "upper_arm.L"},
            binding_method="test-binding",
        )
        clip = MotionClipOutput(
            "Wave",
            object(),
            1,
            25,
            24,
            ("upper_arm.L",),
        )
        self.motion = MotionOutput(
            rig=self.rig,
            armature_object=self.armature,
            implementation_id="test-motion",
            clips=(clip,),
            source_bone_map={"upper_arm.L": "arm_joint_L_1"},
        )

    def output(self, **overrides) -> ExportOutput:
        values = {
            "geometry": self.geometry,
            "implementation_id": "test-export",
            "path": "build/character.glb",
            "format": "glb",
            "size_bytes": 4096,
            "sha256": "a" * 64,
            "object_names": (" Character ", "Armature"),
            "animation_names": (" Wave ",),
            "rig": self.rig,
            "motion": self.motion,
            "metrics": {"triangle_count": 128},
            "metadata": {"generator": "meshvenn"},
        }
        values.update(overrides)
        return ExportOutput(**values)

    def test_output_normalizes_path_format_names_and_mappings(self) -> None:
        output = self.output()
        self.assertIsInstance(output.path, Path)
        self.assertTrue(output.path.is_absolute())
        self.assertEqual(output.path, Path("build/character.glb").resolve(strict=False))
        self.assertEqual(output.format, "GLB")
        self.assertEqual(output.size_bytes, 4096)
        self.assertEqual(output.sha256, "a" * 64)
        self.assertEqual(output.gltf_version, "2.0")
        self.assertEqual(output.mime_type, "model/gltf-binary")
        self.assertEqual(output.implementation_id, "test-export")
        self.assertEqual(output.object_names, ("Character", "Armature"))
        self.assertEqual(output.animation_names, ("Wave",))
        self.assertEqual(output.metrics, {"triangle_count": 128})
        self.assertEqual(output.metadata, {"generator": "meshvenn"})
        self.assertIs(validate_export_output(output), output)

    def test_output_preserves_geometry_rig_and_motion_provenance(self) -> None:
        output = self.output()
        self.assertIs(output.geometry, self.geometry)
        self.assertIs(output.rig, self.rig)
        self.assertIs(output.motion, self.motion)

        static_output = self.output(rig=None, motion=None, animation_names=())
        self.assertIs(static_output.geometry, self.geometry)
        self.assertIsNone(static_output.rig)
        self.assertIsNone(static_output.motion)

    def test_output_accepts_an_absolute_glb_path_and_no_animations(self) -> None:
        path = Path("build/static.glb").resolve(strict=False)
        output = self.output(path=path, rig=None, motion=None, animation_names=(), object_names=("Character",))
        self.assertEqual(output.path, path)
        self.assertEqual(output.animation_names, ())

    def test_output_rejects_invalid_path_and_format(self) -> None:
        with self.assertRaises(ValueError):
            self.output(path="")
        with self.assertRaises(ValueError):
            self.output(path="build/character.gltf")
        with self.assertRaises(TypeError):
            self.output(path=object())
        with self.assertRaises(ValueError):
            self.output(format="gltf")

    def test_output_rejects_invalid_size_and_schema(self) -> None:
        with self.assertRaises(TypeError):
            self.output(size_bytes=1.5)
        with self.assertRaises(TypeError):
            self.output(size_bytes=True)
        with self.assertRaises(ValueError):
            self.output(size_bytes=0)
        with self.assertRaises(ValueError):
            self.output(schema_version=2)

    def test_output_rejects_invalid_implementation_hash_and_gltf_version(self) -> None:
        with self.assertRaises(ValueError):
            self.output(implementation_id="Invalid Export")
        with self.assertRaises(ValueError):
            self.output(sha256="a" * 63)
        with self.assertRaises(ValueError):
            self.output(sha256="A" * 64)
        with self.assertRaises(ValueError):
            self.output(sha256="g" * 64)
        with self.assertRaises(ValueError):
            self.output(gltf_version="1.0")
        with self.assertRaises(ValueError):
            self.output(mime_type="model/gltf+json")

    def test_output_rejects_inconsistent_provenance(self) -> None:
        with self.assertRaises(TypeError):
            self.output(geometry=object())
        with self.assertRaises(TypeError):
            self.output(rig=object(), motion=None)
        with self.assertRaises(TypeError):
            self.output(motion=object())
        with self.assertRaises(ValueError):
            self.output(rig=None)

        other_mesh = object()
        other_geometry = GeometrySurfaceOutput(
            blender_object=other_mesh,
            source=object(),
            projection_space=GeometryProjectionSpace(8, 8, 16),
            implementation_id="other-geometry",
        )
        other_rig = RigOutput(
            geometry=other_geometry,
            blender_object=other_mesh,
            armature_object=object(),
            implementation_id="other-rig",
            semantic_bones={"upper_arm.L": "upper_arm.L"},
            binding_method="test-binding",
        )
        with self.assertRaises(ValueError):
            self.output(rig=other_rig, motion=None)
        with self.assertRaises(ValueError):
            self.output(rig=other_rig)

    def test_output_rejects_invalid_object_and_animation_manifests(self) -> None:
        with self.assertRaises(ValueError):
            self.output(object_names=())
        with self.assertRaises(ValueError):
            self.output(object_names=("Character", " "))
        with self.assertRaises(ValueError):
            self.output(object_names=("Character", "Character"))
        with self.assertRaises(ValueError):
            self.output(animation_names=("Walk", " Walk "))
        with self.assertRaises(ValueError):
            self.output(object_names=("Armature",))
        with self.assertRaises(ValueError):
            self.output(object_names=("Character",))
        with self.assertRaises(ValueError):
            self.output(motion=None, animation_names=("Walk",))
        with self.assertRaises(ValueError):
            self.output(animation_names=("Idle", "Walk"))

    def test_output_rejects_invalid_metrics_and_metadata(self) -> None:
        with self.assertRaises(TypeError):
            self.output(metrics=())
        with self.assertRaises(ValueError):
            self.output(metadata={" ": "invalid"})

    def test_context_accessor_requires_a_typed_export_output(self) -> None:
        output = self.output()
        context = PipelineContext()
        context.set_output(PipelineStage.EXPORT, output)
        self.assertIs(require_export_output(context), output)

        context.set_output(PipelineStage.EXPORT, object())
        with self.assertRaises(TypeError):
            require_export_output(context)

    def test_validator_rejects_untyped_values(self) -> None:
        with self.assertRaises(TypeError):
            validate_export_output(object())


if __name__ == "__main__":
    unittest.main()
