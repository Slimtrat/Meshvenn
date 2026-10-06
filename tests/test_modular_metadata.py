from __future__ import annotations

import copy
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

from core.modular_character import (
    CoordinateConvention, ModularCharacterSpec, NormalizationConvention,
    RegionSpec, SeamDeclarations, SocketSpec,
)


_MODULE_PATH = Path(__file__).resolve().parents[1] / "implementations/glb_export/modular_metadata.py"
_IMPORT_SPEC = importlib.util.spec_from_file_location("meshvenn_modular_metadata_test", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_IMPORT_SPEC)
_IMPORT_SPEC.loader.exec_module(_MODULE)


def modular_spec():
    return ModularCharacterSpec(
        rig_id="canonical-biped-v2", rig_version=2,
        coordinates=CoordinateConvention(NormalizationConvention(True, 2.0, 0.5)),
        regions=(RegionSpec("core", "body-core", "Core_Node"),
                 RegionSpec("arm-left", "left-arm", "Arm_Node"),
                 RegionSpec("leg-right", "right-leg", "Leg_Node")),
        ownership={"SourceMesh": ("core", "arm-left", "leg-right")},
        ownership_source_sha256={"SourceMesh": "a" * 64}, seams=SeamDeclarations(),
        sockets=(SocketSpec("socket-hand-left", "left-arm", "hand.L", "arm-left",
                            (0.1, 0.2, -0.3), (0, 0, 0, 1), (1, 1, 1)),
                 SocketSpec("socket-head", "head", "head", "core",
                            (0, 0.25, 0), (0, 0, 0, 1), (1, 1, 1))))


def document():
    return {
        "asset": {"version": "2.0", "extras": {"preserved": {"tool": "Meshvenn"}}},
        "nodes": [{"name": "Core_Node", "mesh": 0, "skin": 0, "extras": {"meshvenn_region_id": "core"}},
                  {"name": "Arm_Node", "mesh": 1, "skin": 0, "extras": {"meshvenn_region_id": "arm-left"}},
                  {"name": "Leg_Node", "mesh": 2, "skin": 0, "extras": {"meshvenn_region_id": "leg-right"}},
                  {"name": "root", "children": [4, 5]}, {"name": "hand.L"}, {"name": "head"}],
        "meshes": [{"primitives": []}, {"primitives": []}, {"primitives": []}],
        "skins": [{"joints": [3, 4, 5], "inverseBindMatrices": 0}],
        "accessors": [{"componentType": 5126, "count": 3, "type": "MAT4"}],
        "buffers": [{"byteLength": 16}],
    }


def glb_bytes(source, binary=b"\x00\x01\x02\x03ABCD\x04\x05\x06\x07EFGH"):
    encoded = json.dumps(source, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    body = struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
    if binary is not None:
        body += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def parse_glb(payload):
    magic, version, length = struct.unpack_from("<4sII", payload)
    if (magic, version, length) != (b"glTF", 2, len(payload)):
        raise AssertionError("Output GLB header no longer matches its chunks.")
    offset, chunks = 12, []
    while offset < length:
        size, kind = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunks.append((kind, payload[offset:offset + size]))
        offset += size
    return json.loads(chunks[0][1]), chunks[1:]


class ModularMetadataTests(unittest.TestCase):
    def embed(self, source=None):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "character.glb"
            payload = glb_bytes(source if source is not None else document())
            path.write_bytes(payload)
            envelope = _MODULE.embed_modular_metadata(path, modular_spec())
            updated = path.read_bytes()
        return envelope, updated, payload

    def rejects(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "character.glb"
            payload = glb_bytes(source)
            path.write_bytes(payload)
            with self.assertRaises(ValueError):
                _MODULE.embed_modular_metadata(path, modular_spec())
            self.assertEqual(path.read_bytes(), payload, "Failed metadata validation must not mutate the GLB.")

    def test_three_region_ids_bind_exactly_to_mesh_nodes_and_the_shared_skin(self):
        envelope, updated, original = self.embed()
        parsed, binary_chunks = parse_glb(updated)
        self.assertEqual(envelope["spec"], modular_spec().to_dict())
        self.assertEqual(envelope["bindings"]["region_nodes"], {"core": 0, "arm-left": 1, "leg-right": 2})
        self.assertEqual(envelope["bindings"]["skin"], 0)
        self.assertEqual(envelope["bindings"]["joint_nodes"], {"root": 3, "hand.L": 4, "head": 5})
        self.assertEqual(parsed["asset"]["extras"][_MODULE.MODULAR_EXTRAS_KEY], envelope)
        self.assertEqual(parsed["asset"]["extras"]["preserved"], {"tool": "Meshvenn"})
        self.assertEqual(binary_chunks, parse_glb(original)[1], "Metadata must preserve BIN bytes exactly.")
        for key in ("nodes", "meshes", "skins", "accessors", "buffers"):
            self.assertEqual(parsed[key], document()[key], key)

    def test_sockets_bind_owner_regions_and_native_parent_joints_without_extra_nodes(self):
        envelope, updated, _ = self.embed()
        self.assertEqual(envelope["bindings"]["sockets"], {
            "socket-hand-left": {"parent_joint_node": 4, "owner_region_node": 1},
            "socket-head": {"parent_joint_node": 5, "owner_region_node": 0}})
        self.assertEqual(len(parse_glb(updated)[0]["nodes"]), 6)
        self.assertEqual(envelope["spec"]["sockets"][0]["translation"], [0.1, 0.2, -0.3])
        self.assertEqual(envelope["spec"]["sockets"][0]["frame"], "gltf-joint-local")

    def test_staging_alias_is_resolved_by_stable_id_without_changing_other_nodes(self):
        source = document()
        source["nodes"][0]["name"] = "Core_Node.001"
        _, updated, _ = self.embed(source)
        parsed, _ = parse_glb(updated)
        self.assertEqual(parsed["nodes"][0]["name"], "Core_Node")
        self.assertEqual(parsed["nodes"][3:], source["nodes"][3:])
        source["nodes"][4]["name"] = "Core_Node"
        self.rejects(source)

    def test_missing_or_ambiguous_region_nodes_and_mesh_references_fail(self):
        mutations = [lambda d: d["nodes"].pop(0),
                     lambda d: d["nodes"].append(copy.deepcopy(d["nodes"][0])),
                     lambda d: d["nodes"][0].pop("mesh"),
                     lambda d: d["nodes"][0].update(mesh=99),
                     lambda d: d["nodes"][0].update(mesh=-1),
                     lambda d: d["nodes"][0].update(mesh=True)]
        for mutate in mutations:
            source = document()
            mutate(source)
            with self.subTest(source=source):
                self.rejects(source)

    def test_no_skin_dangling_skin_and_replacement_skin_fail(self):
        mutations = [lambda d: d["nodes"][0].pop("skin"),
                     lambda d: d.update(skins=[]), lambda d: d["nodes"][0].update(skin=99),
                     lambda d: d["nodes"][0].update(skin=-1),
                     lambda d: [node.update(skin=False) for node in d["nodes"][:3]]]
        for mutate in mutations:
            source = document()
            mutate(source)
            self.rejects(source)
        source = document()
        source["skins"].append(copy.deepcopy(source["skins"][0]))
        source["nodes"][0]["skin"] = 1
        self.rejects(source)
        for node in source["nodes"][:3]:
            node["skin"] = 1
        self.rejects(source)

    def test_dangling_ambiguous_empty_or_replaced_native_joint_references_fail(self):
        mutations = [lambda d: d["skins"][0].update(joints=[]),
                     lambda d: d["skins"][0].update(joints=[3, 4, 99]),
                     lambda d: d["skins"][0].update(joints=[3, 4, -1]),
                     lambda d: d["skins"][0].update(joints=[3, 4, True]),
                     lambda d: d["skins"][0].update(joints=[3, 4, 4]),
                     lambda d: d["nodes"][5].update(name="hand.L"),
                     lambda d: d["nodes"][5].update(name="replacement-head"),
                     lambda d: d["nodes"][3].pop("name")]
        for mutate in mutations:
            source = document()
            mutate(source)
            with self.subTest(source=source):
                self.rejects(source)

    def test_invalid_glb_header_and_truncated_chunks_fail_without_overwrite(self):
        payloads = [b"bad!" + glb_bytes(document())[4:], glb_bytes(document())[:-4]]
        valid = glb_bytes(document())
        payloads.append(valid[:12] + struct.pack("<II", len(valid) * 2, 0x4E4F534A) + valid[20:])
        for payload in payloads:
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "bad.glb"
                path.write_bytes(payload)
                with self.assertRaises(ValueError):
                    _MODULE.embed_modular_metadata(path, modular_spec())
                self.assertEqual(path.read_bytes(), payload)

    def test_existing_modular_contract_is_not_silently_replaced(self):
        source = document()
        source["asset"]["extras"][_MODULE.MODULAR_EXTRAS_KEY] = {"spec": {"version": 99}}
        self.rejects(source)
