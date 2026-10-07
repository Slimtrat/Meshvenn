"""One explicit normalization contract; missing evidence is not a default."""
from dataclasses import FrozenInstanceError, replace
import math
import unittest

from core.geometry_contracts import GeometryNormalization, validate_geometry_surface_output
from core.geometry_contracts.normalization import NATIVE_OBJECT_SCALE
from tests.geometry_contracts_test_support import geometry_output


class GeometryNormalizationTests(unittest.TestCase):
    def test_explicit_normalization_is_immutable_and_roundtrips(self):
        value = GeometryNormalization(True, 1.82, .02, NATIVE_OBJECT_SCALE)
        self.assertEqual(value, GeometryNormalization.from_dict(value.to_dict()))
        with self.assertRaises(FrozenInstanceError):
            value.scale = 2
        self.assertIs(replace(geometry_output(), normalization=value).normalization, value)

    def test_disabled_and_uncertified_are_distinct(self):
        self.assertIsNone(geometry_output().normalization)
        disabled = GeometryNormalization(False, None, 1., NATIVE_OBJECT_SCALE)
        self.assertFalse(disabled.normalized_height)
        for enabled, target, scale in ((1, 1.82, .02), (False, 1.82, 1), (False, None, .5),
                                       (True, None, 1), (True, True, 1), (True, math.nan, 1),
                                       (True, 1.82, True), (True, 1.82, 0), (True, 1.82, math.inf)):
            with self.assertRaises((TypeError, ValueError)):
                GeometryNormalization(enabled, target, scale, NATIVE_OBJECT_SCALE)
        with self.assertRaises(ValueError):
            GeometryNormalization(True, 1.82, .02, "guess")

    def test_diagnostics_cannot_contradict_or_supply_the_contract(self):
        claims = {"normalized_height": True, "target_height": 1.82, "normalization_scale": .02}
        output = geometry_output(metadata=claims)
        self.assertIsNone(output.normalization)
        value = GeometryNormalization(True, 1.82, .02, NATIVE_OBJECT_SCALE)
        surface = replace(output, normalization=value)
        for key, wrong in (("normalized_height", False), ("normalized_height", 1),
                           ("target_height", 3), ("normalization_scale", math.nan)):
            with self.assertRaises(ValueError):
                replace(surface, metrics={key: wrong})
        # Diagnostic dicts are mutable; the publication accessor rechecks them.
        surface.metadata["normalization_scale"] = 2
        with self.assertRaisesRegex(ValueError, "contradicts"):
            validate_geometry_surface_output(surface)
        with self.assertRaises(TypeError):
            replace(output, normalization=claims)

    def test_saved_contract_rejects_unknown_or_missing_fields(self):
        value = GeometryNormalization(True, 1.82, .02, NATIVE_OBJECT_SCALE).to_dict()
        for invalid in ({}, {**value, "fallback": True}, {k: v for k, v in value.items() if k != "provenance"}):
            with self.assertRaises(ValueError):
                GeometryNormalization.from_dict(invalid)


if __name__ == "__main__":
    unittest.main()
