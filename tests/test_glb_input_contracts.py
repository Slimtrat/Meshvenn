from __future__ import annotations

import unittest
from pathlib import Path

from core.glb_input_contracts import (
    GLBFileInputOutput,
    require_glb_file_input,
    validate_glb_file_input,
)
from core.pipeline_contracts import PipelineContext, PipelineStage


def _output(**overrides) -> GLBFileInputOutput:
    values = {
        "path": Path("character.glb"),
        "implementation_id": "glb-file-v1",
        "size_bytes": 1024,
        "sha256": "a" * 64,
        "node_names": ("Character",),
        "animation_names": ("Walk",),
        "scene_count": 1,
        "mesh_count": 1,
        "skin_count": 1,
        "material_count": 2,
    }
    values.update(overrides)
    return GLBFileInputOutput(**values)


class GLBInputContractTests(unittest.TestCase):
    def test_normalizes_valid_glb_input(self) -> None:
        output = _output()
        self.assertTrue(output.path.is_absolute())
        self.assertTrue(output.animated)
        self.assertTrue(output.skinned)
        self.assertEqual(output.gltf_version, "2.0")

    def test_rejects_invalid_artifact_metadata(self) -> None:
        with self.assertRaises(ValueError):
            _output(path="character.gltf")
        with self.assertRaises(ValueError):
            _output(sha256="A" * 64)
        with self.assertRaises(ValueError):
            _output(mesh_count=0)
        with self.assertRaises(ValueError):
            _output(animation_names=("Walk", ""))

    def test_accepts_duplicate_source_labels_allowed_by_gltf(self) -> None:
        output = _output(
            node_names=("Bone", "Bone"),
            animation_names=("Walk", "Walk"),
        )
        self.assertEqual(output.node_names, ("Bone", "Bone"))
        self.assertEqual(output.animation_names, ("Walk", "Walk"))

    def test_context_accessor_requires_typed_input(self) -> None:
        context = PipelineContext()
        context.set_output(PipelineStage.INPUT, _output())
        self.assertIs(require_glb_file_input(context), context.get_output(PipelineStage.INPUT))
        with self.assertRaises(TypeError):
            validate_glb_file_input(object())


if __name__ == "__main__":
    unittest.main()
