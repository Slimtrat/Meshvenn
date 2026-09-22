"""Offline integrity and glTF structure checks for the V2 reference corpus."""

from __future__ import annotations

import hashlib
import json
import struct
import unittest
from pathlib import Path


EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "example" / "v2"
MANIFEST = EXAMPLE_ROOT / "manifest.json"


def glb_document(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError(f"Truncated GLB: {path}")
    magic, version, declared_length = struct.unpack_from("<4sII", data)
    if (magic, version, declared_length) != (b"glTF", 2, len(data)):
        raise ValueError(f"Invalid GLB header: {path}")
    offset = 12
    chunks = []
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError(f"Truncated GLB chunk header: {path}")
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        offset += 8
        if chunk_length % 4 or offset + chunk_length > len(data):
            raise ValueError(f"Invalid GLB chunk length: {path}")
        chunks.append((chunk_type, data[offset:offset + chunk_length]))
        offset += chunk_length
    if not chunks or chunks[0][0] != b"JSON":
        raise ValueError(f"Missing first JSON chunk: {path}")
    document = json.loads(chunks[0][1])
    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError(f"Not a glTF 2.0 asset: {path}")
    if document.get("buffers") and not any(kind == b"BIN\x00" for kind, _ in chunks):
        raise ValueError(f"Missing embedded binary buffer: {path}")
    return document


class V2AssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_corpus_is_pinned_and_complete(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 2)
        self.assertRegex(self.manifest["source"]["revision"], r"^[0-9a-f]{40}$")
        assets = self.manifest["assets"]
        self.assertEqual(len(assets), 7)
        self.assertEqual(len({asset["id"] for asset in assets}), len(assets))
        listed = {asset["file"] for asset in assets}
        actual = {path.relative_to(EXAMPLE_ROOT).as_posix() for path in (EXAMPLE_ROOT / "assets").glob("*.glb")}
        self.assertEqual(listed, actual)
        self.assertEqual(sum(asset["skins"] > 0 for asset in assets), 3)

    def test_bytes_hashes_licenses_and_gltf_structure(self) -> None:
        for asset in self.manifest["assets"]:
            with self.subTest(asset=asset["id"]):
                relative = Path(asset["file"])
                self.assertEqual(relative.parts[0], "assets")
                self.assertEqual(len(relative.parts), 2)
                path = EXAMPLE_ROOT / relative
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, asset["bytes"])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["sha256"])
                self.assertIn(asset["license"], {"CC0-1.0", "CC-BY-4.0", "CC0-1.0 AND CC-BY-4.0"})
                self.assertTrue(asset["credit"])
                document = glb_document(path)
                for field in ("meshes", "skins", "animations"):
                    self.assertEqual(len(document.get(field, [])), asset[field])
                self.assertTrue(all(mesh.get("primitives") for mesh in document["meshes"]))


if __name__ == "__main__":
    unittest.main()
