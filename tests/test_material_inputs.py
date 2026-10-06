"""The optional appearance route cannot replace or miscalibrate geometry."""

from dataclasses import replace
from types import SimpleNamespace
from array import array
import sys
import unittest
from unittest.mock import patch

from core.geometry_contracts import GeometryProjectionSpace
from core.material_inputs import MaterialProjectionInput
from core.pipeline_contracts import PipelineContext
from scripts.modular_appearance_evidence import image_signal, certify_appearance
from core.image_mask import BinaryMask


def view(name="front", angle=0, size=16):
    return ProjectedMaterialView.from_image_buffer(name=name, azimuth_degrees=angle,
        elevation_degrees=0, image_buffer=ImageBuffer(size, size, array("f", [.8, .4, .04, 1]) * (size * size)),
        mask=BinaryMask(size, size, bytes([1]) * (size * size)))


class MaterialInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blender_stub = patch.dict(sys.modules, {"bpy": SimpleNamespace()})
        cls.blender_stub.start()
        global ProjectedMaterialView, ImageBuffer
        from core.projected_material import ProjectedMaterialView, ImageBuffer

    @classmethod
    def tearDownClass(cls):
        cls.blender_stub.stop()

    def setUp(self):
        self.frame = GeometryProjectionSpace(64, 64, 64)
        self.geometry = SimpleNamespace(projection_space=self.frame,
                                        source=SimpleNamespace(material_views=(view(),)))
        self.appearance = MaterialProjectionInput((view(),), self.frame, "a" * 64, "base-color-emission")

    def test_default_context_leaves_geometry_source_unchanged(self):
        self.assertIsNone(PipelineContext().material_input)
        self.appearance.validate_for(self.geometry)
        self.assertEqual(self.geometry.source.material_views[0].transform.azimuth_degrees, 0)
        self.assertNotIn("mesh", self.appearance.__dict__)
        self.assertNotIn("rig", self.appearance.__dict__)

    def test_wrong_frame_and_camera_fail_instead_of_neutral_fallback(self):
        wrong = replace(self.appearance, projection_space=GeometryProjectionSpace(32, 32, 32))
        with self.assertRaisesRegex(ValueError, "frame"):
            wrong.validate_for(self.geometry)
        for candidate in (view("back"), view(angle=90), view(size=32)):
            with self.assertRaisesRegex(ValueError, "camera"):
                replace(self.appearance, views=(candidate,)).validate_for(self.geometry)

    def test_duplicates_unknown_version_and_unverified_provenance_fail(self):
        for kwargs in ({"views": (view(), view())}, {"version": 2}, {"version": True},
                       {"source_sha256": ""}, {"render_mode": "neutral"}):
            with self.assertRaises(ValueError):
                replace(self.appearance, **kwargs)

    def test_opaque_objects_and_invalid_buffers_cannot_carry_source_geometry(self):
        for candidate in (SimpleNamespace(name="front", rig=object()),
                          replace(view(), image=object()), replace(view(), mask=None),
                          replace(view(), image=ImageBuffer(16, 16, array("f", [1]))),
                          replace(view(), mask=BinaryMask(8, 8, bytes([1]) * 64))):
            with self.assertRaises(TypeError):
                replace(self.appearance, views=(candidate,))
        with self.assertRaisesRegex(ValueError, "binary"):
            replace(self.appearance, views=(replace(view(), mask=BinaryMask(16, 16, bytes([2]) * 256)),))
        corrupted = view()
        corrupted.image.pixels[0] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            replace(self.appearance, views=(corrupted,))
        self.appearance.views[0].image.pixels[0] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            self.appearance.validate_for(self.geometry)

    def test_signal_excludes_padding_and_empty_atlas(self):
        signal = image_signal([.8, .4, .04, 1, 1, 1, 1, 1], [1, 0])
        self.assertEqual(signal["occupied_pixels"], 1)
        self.assertEqual(signal["chromatic_fraction"], 1)
        self.assertEqual(signal["white_fraction"], 0)
        for pixels, occupied in (([float("nan"), 0, 0, 1], [1]), ([0, 0, 0, 1], [0])):
            with self.assertRaises(ValueError):
                image_signal(pixels, occupied)

    def test_white_atlas_cannot_pass_despite_full_coverage(self):
        stats = SimpleNamespace(texture_width=512, samples_per_axis=2, surface_samples=100,
                                fallback_samples=0, selected_source_samples=100)
        bake = SimpleNamespace(stats=stats, texture=SimpleNamespace(pixels=[1, 1, 1, 1]), coverage=[1])
        source = [{"name": str(index), "chromatic_fraction": 1, "white_fraction": 0,
                   "occupied_pixels": 1} for index in range(10)]
        counters = dict(total_samples=1000, candidate_samples=1000, source_rejected_samples=0,
                        visible_samples=1000, occluded_samples=0, front_facing_samples=1000,
                        backface_samples=0, grazing_rejected_samples=0, primary_samples=100,
                        projected_fallback_samples=0, neutral_fallback_samples=0, selected_samples=100)
        with self.assertRaisesRegex(AssertionError, "appearance gate"):
            certify_appearance(bake, counters, source)
        bake.texture.pixels = [.8, .4, .04, 1]
        for wrong in ({}, {**counters, "neutral_fallback_samples": 10}, {**counters, "primary_samples": -1}):
            with self.assertRaises(ValueError):
                certify_appearance(bake, wrong, source)
        self.assertTrue(certify_appearance(bake, counters, source)["passed"])


if __name__ == "__main__":
    unittest.main()
