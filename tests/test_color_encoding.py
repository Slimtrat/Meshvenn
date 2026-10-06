from array import array
import unittest
from core.color_encoding import linear_to_srgb, encode_srgb_rgba


class ColorEncodingTests(unittest.TestCase):
    def test_known_nonprimary_linear_colors_encode_not_double_decode(self):
        for linear, encoded in ((.25, .5370987305), (.5, .7353569831), (.75, .8808250211),
                                (0, 0), (.001, .01292), (1, 1)):
            self.assertAlmostEqual(linear_to_srgb(linear), encoded, places=9)

    def test_alpha_linear_and_source_buffer_unchanged(self):
        source = array("f", [.25, .5, .75, .3])
        encoded = encode_srgb_rgba(source)
        self.assertAlmostEqual(encoded[3], .3, places=6)
        self.assertAlmostEqual(source[0], .25)
        self.assertAlmostEqual(encoded[0], .5370987305, places=6)

    def test_invalid_buffers_fail_closed(self):
        for values in ([0], [float("nan"), 0, 0, 1], [-1, 0, 0, 1], [0, 0, 0, 2]):
            with self.assertRaises(ValueError):
                encode_srgb_rgba(values)


if __name__ == "__main__":
    unittest.main()
