"""Exact-file and embedded-resource checks use the shipped original GLB."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.character_quality.authority import source_authority
from scripts.character_quality.delivery import inspect_delivery, _reader
from scripts.diagnostic_qualification.integrity import sha256_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/diagnostics/provider-v1/original-reference.glb"


def glb_bytes(document, binary):
    encoded = json.dumps(document, allow_nan=False, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    data = binary + b"\0" * (-len(binary) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(encoded) + len(data)) +
            struct.pack("<I4s", len(encoded), b"JSON") + encoded + struct.pack("<I4s", len(data), b"BIN\0") + data)


class ExactCharacterDeliveryTests(unittest.TestCase):
    def test_actual_source_resources_are_verified_without_claiming_style(self):
        digest = sha256_file(SOURCE)
        result = inspect_delivery(SOURCE, digest)
        self.assertEqual(result["glb_sha256"], digest)
        self.assertEqual(result["triangle_definition_count"], 26204)
        self.assertEqual(result["mesh_definitions"], 31)
        self.assertEqual(result["external_resources"], 0)
        self.assertEqual(result["visual_quality"], "unknown")
        self.assertEqual(result["animated_use"], "unknown")

    def test_stale_hash_and_definition_budgets_fail_closed(self):
        with self.assertRaises(ValueError):
            inspect_delivery(SOURCE, "0" * 64)
        with self.assertRaises(ValueError):
            inspect_delivery(SOURCE, sha256_file(SOURCE), max_triangles=10)

    def test_rehashed_external_resources_and_invalid_indices_are_rejected(self):
        original = SOURCE.read_bytes()
        reader = _reader()[0]
        for mutation in ("resource", "indices"):
            document, binary = reader["read_glb"](SOURCE)
            if mutation == "resource":
                document["images"] = [{"uri": "https://invalid.example/texture.png"}]
            else:
                accessor = document["accessors"][document["meshes"][0]["primitives"][0]["indices"]]
                view = document["bufferViews"][accessor["bufferView"]]
                offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                data = bytearray(binary)
                component = {5121: ("B",255), 5123: ("H",65535), 5125: ("I",2**32-1)}[accessor["componentType"]]
                struct.pack_into("<" + component[0], data, offset, component[1])
                binary = bytes(data)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "changed.glb"
                path.write_bytes(glb_bytes(document, binary))
                with self.assertRaises(ValueError):
                    inspect_delivery(path, sha256_file(path))
        self.assertEqual(SOURCE.read_bytes(), original)

    def test_semantic_regions_require_the_exact_original_source(self):
        known = source_authority(sha256_file(SOURCE))
        self.assertEqual(known["authority_status"], "source_authored")
        self.assertIn("right_flag_pole", {r["region_id"] for r in known["regions"]})
        probe = next(r for r in known["regions"] if r["region_id"] == "antenna_free_stem")
        head = next(r for r in known["regions"] if r["region_id"] == "head")
        self.assertGreater(probe["bounds"][0][2], head["bounds"][1][2])
        self.assertTrue(known["source_only_thin_probe"]["rule"].startswith("Middle half"))
        other = source_authority("a" * 64)
        self.assertEqual(other["authority_status"], "unknown")
        self.assertEqual(other["regions"], [])
        self.assertNotEqual(other["frame_id"], known["frame_id"])


if __name__ == "__main__":
    unittest.main()
