from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "implementations/glb_export/modular_gltf.py"
SPEC = importlib.util.spec_from_file_location("modular_gltf_reader", MODULE_PATH)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


def _glb(document, binary):
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    body = struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, len(body) + 12) + body


def _document(binary, component=5126, kind="VEC3", count=2):
    return {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(binary)}],
            "accessors": [{"bufferView": 0, "componentType": component, "count": count, "type": kind}]}


class ModularGLTFReaderTests(unittest.TestCase):
    def test_embedded_bin_and_float_vectors(self):
        binary = struct.pack("<6f", 1, 2, 3, -4, -5, -6)
        document = _document(binary)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.glb"
            path.write_bytes(_glb(document, binary))
            actual, data = reader.read_glb(path)
        self.assertEqual(actual, document)
        self.assertEqual(data, binary)
        self.assertEqual(reader.read_accessor(actual, data, 0), ((1, 2, 3), (-4, -5, -6)))

    def test_interleaved_accessor_and_offset(self):
        binary = struct.pack("<8f", 99, 1, 2, 3, 99, 4, 5, 6)
        document = _document(binary)
        document["bufferViews"][0]["byteStride"] = 16
        document["accessors"][0]["byteOffset"] = 4
        self.assertEqual(reader.read_accessor(document, binary, 0), ((1, 2, 3), (4, 5, 6)))

    def test_normalized_color_and_signed_values(self):
        binary = bytes((0, 127, 255, 255, 255, 0, 127, 255))
        document = _document(binary, 5121, "VEC4")
        document["accessors"][0]["normalized"] = True
        self.assertEqual(reader.read_accessor(document, binary, 0)[0], (0, 127 / 255, 1, 1))
        signed = struct.pack("<4b", -128, -127, 0, 127)
        document = _document(signed, 5120, "VEC4", 1)
        document["accessors"][0]["normalized"] = True
        self.assertEqual(reader.read_accessor(document, signed, 0), ((-1, -1, 0, 1),))

    def test_mat4_accessor(self):
        binary = struct.pack("<16f", *range(16))
        self.assertEqual(reader.read_accessor(_document(binary, kind="MAT4", count=1), binary, 0), (tuple(range(16)),))

    def test_rejects_bad_accessor_bounds_alignment_and_float(self):
        binary = struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        mutations = (("count", 3), ("count", True), ("byteOffset", 1),
                     ("componentType", 7000), ("bufferView", 1), ("sparse", {}), ("normalized", True))
        for key, value in mutations:
            document = _document(binary)
            document["accessors"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                reader.read_accessor(document, binary, 0)
        binary = struct.pack("<3f", float("nan"), 0, 1)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            reader.read_accessor(_document(binary, count=1), binary, 0)

    def test_rejects_external_buffers_and_truncated_headers(self):
        binary = struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        document = _document(binary)
        document["buffers"][0]["uri"] = "not-embedded.bin"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.glb"
            path.write_bytes(_glb(document, binary))
            with self.assertRaisesRegex(ValueError, "embedded"):
                reader.read_glb(path)
            path.write_bytes(_glb(_document(binary), binary)[:-4])
            with self.assertRaisesRegex(ValueError, "header"):
                reader.read_glb(path)


if __name__ == "__main__":
    unittest.main()
