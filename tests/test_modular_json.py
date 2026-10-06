from __future__ import annotations

import unittest

from core.modular_character.json_io import strict_json_loads


class ModularJSONTests(unittest.TestCase):
    def test_ordinary_json_preserves_ordered_face_ownership(self):
        value = strict_json_loads('{"version":1,"ownership":{"Mesh":["left-arm","body-core"]}}')
        self.assertEqual(value["ownership"]["Mesh"], ["left-arm", "body-core"])

    def test_duplicate_keys_fail_at_every_nesting_level(self):
        for value in ('{"version":99,"version":1}',
                      '{"ownership":{"Mesh":["left-arm"],"Mesh":["body-core"]}}',
                      '{"sockets":[{"id":"left","id":"right"}]}'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "duplicate key"):
                strict_json_loads(value)

    def test_non_json_float_constants_are_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Non-finite"):
                strict_json_loads('{"value":' + value + '}')
