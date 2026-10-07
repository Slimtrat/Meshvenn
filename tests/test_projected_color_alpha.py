"""Coverage-aware filtering removes mattes without changing source confidence."""

from array import array
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


class ProjectedColorAlphaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub = patch.dict(sys.modules, {'bpy': SimpleNamespace()})
        cls.stub.start()
        from core.projected_material import ImageBuffer, ProjectedMaterialView
        from core.projected_material.sampling import _sample_source_view
        from core.projected_material.blending import _blend_projected_color_detailed
        cls.buffer_type, cls.view_type = ImageBuffer, ProjectedMaterialView
        cls.sample_source = staticmethod(_sample_source_view)
        cls.blend = staticmethod(_blend_projected_color_detailed)

    @classmethod
    def tearDownClass(cls):
        cls.stub.stop()

    def buffer(self, left, right, mode='STRAIGHT'):
        return self.buffer_type(2, 2, array('f', (*left, *right) * 2), alpha_mode=mode)

    def assertColor(self, actual, expected):
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=6)

    def test_opaque_border_keeps_color_and_filtered_confidence(self):
        image = self.buffer((.8, .4, .04, 1), (0, 0, 0, 0))
        self.assertColor(image.sample_bilinear(.5, .5), (.4, .2, .02, .5))
        self.assertColor(image.sample_bilinear_alpha_aware(.5, .5), (.8, .4, .04, .5))
        # Clamp/corner/single-pixel behavior remains well-defined.
        self.assertColor(image.sample_bilinear_alpha_aware(-1, 2), (.8, .4, .04, 1))
        single = self.buffer_type(1, 1, array('f', (.3, .5, .7, .2)))
        self.assertColor(single.sample_bilinear_alpha_aware(.7, .8), (.3, .5, .7, .2))

    def test_transparent_matte_and_empty_kernel_do_not_invent_color(self):
        image = self.buffer((.3, .5, .7, 1), (1, 0, 1, 0))
        self.assertColor(image.sample_bilinear_alpha_aware(.75, .5), (.3, .5, .7, .25))
        self.assertColor(image.sample_bilinear_alpha_aware(1, .5), (0, 0, 0, 0))

    def test_partial_alpha_uses_coverage_weighted_color(self):
        image = self.buffer((1, 0, 0, .25), (0, 0, 1, .75))
        self.assertColor(image.sample_bilinear_alpha_aware(.5, .5), (.25, 0, .75, .5))

    def test_four_corner_filter_weights_both_axes(self):
        image = self.buffer_type(2, 2, array('f', (1, 0, 0, 1, 0, 1, 0, .5,
                                                  0, 0, 1, .25, 1, 1, 1, 0)))
        self.assertColor(image.sample_bilinear_alpha_aware(.25, .75),
                         (12 / 23, 2 / 23, 9 / 23, 23 / 64))

    def test_premul_is_not_multiplied_twice(self):
        straight = self.buffer((1, 0, 0, .25), (0, 0, 1, .75))
        premul = self.buffer((.25, 0, 0, .25), (0, 0, .75, .75), 'PREMUL')
        for u in (0, .2, .5, .8, 1):
            self.assertColor(premul.sample_bilinear_alpha_aware(u, .5),
                             straight.sample_bilinear_alpha_aware(u, .5))

    def test_none_is_opaque_and_packed_alpha_fails_closed(self):
        image = self.buffer((1, 0, 0, 0), (0, 0, 1, .5), 'NONE')
        self.assertColor(image.sample_bilinear_alpha_aware(.5, .5), (.5, 0, .5, 1))
        for mode in ('CHANNEL_PACKED', 'unknown'):
            with self.assertRaisesRegex(ValueError, 'coverage alpha'):
                self.buffer((1, 0, 0, 1), (0, 0, 0, 0), mode).sample_bilinear_alpha_aware(.5, .5)

    def test_nonfinite_coverage_or_covered_rgb_rejected(self):
        for rgba in ((1, 0, 0, float('nan')), (1, 0, 0, -1), (float('nan'), 0, 0, 1)):
            with self.assertRaises(ValueError):
                self.buffer(rgba, rgba).sample_bilinear_alpha_aware(.5, .5)
            with self.assertRaises(ValueError):
                self.buffer(rgba, rgba).validate_coverage_data()

    def test_prevalidation_ignores_unused_channels_and_preserves_legacy_hdr(self):
        self.buffer((float('nan'), 0, 0, 0), (2, -1, .5, 1)).validate_coverage_data()
        self.buffer((2, -1, .5, float('nan')), (2, -1, .5, -1), 'NONE').validate_coverage_data()
        for invalid in (self.buffer_type(0, 2, array('f')),
                        self.buffer_type(2, 2, array('f', (1, 0, 0, 1)))):
            with self.assertRaisesRegex(ValueError, 'dimensions'):
                invalid.validate_coverage_data()

    def test_opaque_images_remain_identical_to_historical_filter(self):
        image = self.buffer((.2, .8, .4, 1), (.7, .1, .6, 1))
        for u in (0, .2, .5, .8, 1):
            self.assertColor(image.sample_bilinear_alpha_aware(u, .5), image.sample_bilinear(u, .5))

    def test_blender_ingress_records_alpha_association_without_mutation(self):
        values = array('f', (.1, .2, .3, .5))
        class Pixels:
            def foreach_get(self, output):
                output[:] = values
        image = SimpleNamespace(size=(1, 1), name='premul', alpha_mode='PREMUL',
                                pixels=Pixels(), update=lambda: None)
        buffer = self.buffer_type.from_blender_image(image)
        self.assertEqual(buffer.alpha_mode, 'PREMUL')
        self.assertColor(buffer.rgba(0, 0), values)
        self.assertColor(buffer.sample_bilinear_alpha_aware(.5, .5), (.2, .4, .6, .5))
        self.assertEqual(image.alpha_mode, 'PREMUL')

    def test_loaded_float_png_records_rna_premul_not_straight_file_label(self):
        values = array('f', (.125, .25, .375, .5))
        class Pixels:
            def foreach_get(self, output):
                output[:] = values
        image = SimpleNamespace(size=(1, 1), name='PNG16', source='FILE', is_float=True,
                 alpha_mode='STRAIGHT', colorspace_settings=SimpleNamespace(name='sRGB'),
                 pixels=Pixels(), update=lambda: None)
        buffer = self.buffer_type.from_blender_image(image)
        self.assertEqual(buffer.source_alpha_mode, 'STRAIGHT')
        self.assertEqual(buffer.alpha_mode, 'PREMUL')
        self.assertEqual(buffer.rgb_encoding, 'scene-linear')
        self.assertColor(buffer.rgba(0, 0), values)
        self.assertColor(buffer.sample_bilinear_alpha_aware(.5, .5), (.25, .5, .75, .5))

    def test_loaded_byte_srgb_normalizes_only_projected_sampling(self):
        from math import pow
        expected = (.25, .5, .75)
        encoded = tuple(1.055 * pow(value, 1 / 2.4) - .055 for value in expected)
        values = array('f', (*encoded, .5))
        image = SimpleNamespace(source='FILE', is_float=False, alpha_mode='STRAIGHT',
                                 colorspace_settings=SimpleNamespace(name='sRGB'))
        buffer = self.buffer_type.from_copied_blender_pixels(image, values, width=1, height=1)
        self.assertIs(buffer.pixels, values)
        self.assertEqual(buffer.rgb_encoding, 'sRGB')
        self.assertColor(buffer.sample_bilinear(.5, .5), (*encoded, .5))
        self.assertColor(buffer.sample_bilinear_alpha_aware(.5, .5), (*expected, .5))

    def test_srgb_premul_is_unassociated_before_nonlinear_conversion(self):
        from math import pow
        expected = (.25, .5, .75)
        encoded = tuple(1.055 * pow(value, 1 / 2.4) - .055 for value in expected)
        values = array('f', (*(value * .5 for value in encoded), .5))
        buffer = self.buffer_type(1, 1, values, 'PREMUL', 'sRGB')
        self.assertColor(buffer.sample_bilinear_alpha_aware(.5, .5), (*expected, .5))

    def test_noncolor_float_data_association_and_unknown_colorspace_are_explicit(self):
        values = array('f', (.25, .5, .75, .5))
        image = SimpleNamespace(source='FILE', is_float=True, alpha_mode='STRAIGHT',
                                 colorspace_settings=SimpleNamespace(name='Non-Color'))
        buffer = self.buffer_type.from_copied_blender_pixels(image, values, width=1, height=1)
        self.assertEqual(buffer.alpha_mode, 'STRAIGHT')
        self.assertColor(buffer.sample_bilinear_alpha_aware(.5, .5), (.25, .5, .75, .5))
        image.colorspace_settings.name = 'Custom Unknown'
        unknown = self.buffer_type.from_copied_blender_pixels(image, values, width=1, height=1)
        self.assertColor(unknown.sample_bilinear(.5, .5), values)
        with self.assertRaisesRegex(ValueError, 'encoding is not certified'):
            unknown.validate_coverage_data()

    def test_blender_premul_byte_ingress_is_not_claimed_as_qualified(self):
        values = array('f', (.25, .5, .75, .5))
        for source in ('FILE', 'GENERATED'):
            image = SimpleNamespace(source=source, is_float=False, alpha_mode='PREMUL',
                                     colorspace_settings=SimpleNamespace(name='sRGB'))
            buffer = self.buffer_type.from_copied_blender_pixels(image, values, width=1, height=1)
            self.assertColor(buffer.sample_bilinear(.5, .5), values)
            with self.assertRaisesRegex(ValueError, 'premultiplied-byte-ingress'):
                buffer.validate_coverage_data()

    def test_projected_sampling_preserves_mask_alpha_and_opaque_output(self):
        from core.image_mask import BinaryMask
        image = self.buffer((.8, .4, .04, 1), (0, 0, 0, 0))
        view = self.view_type.from_image_buffer(name='front', image_buffer=image,
                 azimuth_degrees=0, elevation_degrees=0, weight=2,
                 mask=BinaryMask(2, 2, bytes((1, 1, 1, 1))))
        kwargs = dict(width=2, depth=2, height=2, voxel_size=1, center_xy=True)
        candidate = self.sample_source((0, 0, 1), (0, -1, 0), view, **kwargs)
        self.assertIsNotNone(candidate)
        self.assertColor(candidate.color, (.8, .4, .04, .5))
        self.assertAlmostEqual(candidate.base_weight, 1)
        result = self.blend((0, 0, 1), (0, -1, 0), [view], **kwargs)
        self.assertColor(result.color, (.8, .4, .04, 1))
        self.assertFalse(result.used_fallback)
        blocked = self.view_type.from_image_buffer(name='blocked', image_buffer=image,
                   azimuth_degrees=0, elevation_degrees=0,
                   mask=BinaryMask(2, 2, bytes(4)))
        self.assertIsNone(self.sample_source((0, 0, 1), (0, -1, 0), blocked, **kwargs))
        class Occluded:
            def query(self, position, direction):
                return SimpleNamespace(visible=False)
        rejected = self.blend((0, 0, 1), (0, -1, 0), [view], visibility_tester=Occluded(), **kwargs)
        self.assertTrue(rejected.used_fallback)
        self.assertEqual(rejected.occluded_samples, 1)


if __name__ == '__main__':
    unittest.main()
