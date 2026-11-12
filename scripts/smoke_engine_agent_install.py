"""Qualify installed distributions and real MCP-to-native calls outside checkout."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import struct
import sys
import sysconfig
import zlib


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def installed_source_hash(module):
    root = Path(module.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        name, content = path.relative_to(root).as_posix().encode(), path.read_bytes()
        digest.update(len(name).to_bytes(4, "big") + name)
        digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def cube_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"".join(
        bytes((51, 128, 191, 255)) if 7 <= x <= 23 and 7 <= y <= 23 else bytes(4)
        for x in range(31)) for y in range(31))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 31, 31, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def source_arguments():
    from meshvenn_engine.core.diagnostic_contracts import (
        ArtifactReference, CameraDeclaration, ViewRevision, ViewSetRevision,
    )
    from meshvenn_engine.core.diagnostics_preflight import RasterInput
    png = cube_png()
    raster = RasterInput.from_png_bytes(png)
    proof = ArtifactReference("analytic-native16-cell-proof",
        hashlib.sha256(b"cube centres4..11/native16; cameras azimuth0,90/elevation0").hexdigest(),
        "application/x-analytic-camera-proof")
    views = tuple(ViewRevision(name, 1, raster.content_reference(), None,
        CameraDeclaration("orthographic", angle, 0, verified=True, verification_evidence=proof),
        origin="rendered", origin_details="Analytically authored cell fixture; no human asset certification")
        for name, angle in (("front", 0), ("side", 90)))
    revision = ViewSetRevision("installed-agent-cube", 1, views)
    image = {"png_base64": base64.b64encode(png).decode("ascii")}
    return {"view_set": revision.to_dict(), "inputs": {v.view_id: {"image": image} for v in views}}


def complete_artifact(read, reference):
    """Read the public chunk API; never bypass the store via private file paths."""
    data = bytearray()
    while True:
        part = read(reference["sha256"], offset=len(data), limit=65536)
        assert part["status"] == "completed", part
        raw = base64.b64decode(part["data_base64"], validate=True)
        assert part["offset"] == len(data) and part["bytes"] == len(raw)
        assert part["total_bytes"] == reference["bytes"]
        data.extend(raw)
        if part["eof"]:
            break
        assert raw, "Non-final artifact chunk made no progress"
    assert len(data) == reference["bytes"]
    assert hashlib.sha256(data).hexdigest() == reference["sha256"]
    return json.loads(data)


def appearance_arguments():
    """A declared analytic plane, accepted reference and equal original colors."""
    from meshvenn_engine.core.appearance_diagnostics import SurfaceMesh
    from meshvenn_engine.core.diagnostic_contracts import ArtifactReference, CanonicalReference, ViewRevision, ViewSetRevision
    from dataclasses import replace
    base = source_arguments()
    original = ViewSetRevision.from_dict(base["view_set"]).views[0]
    target = replace(original, view_id="target")
    reference = replace(original, view_id="reference", role="reference")
    proof = ArtifactReference("authored-visible-plane", hashlib.sha256(b"normalized plane y=0,xz[-.6,.6]; color=sRGB albedo").hexdigest(), "application/json")
    revision = ViewSetRevision("installed-appearance", 1, (target, reference), CanonicalReference(
        "accepted-analytic-design", 1, reference.image, validated=True, view_ids=("reference",), validation_evidence=proof))
    surface = SurfaceMesh(((-.6,0.,-.6),(.6,0.,-.6),(.6,0.,.6),(-.6,0.,.6)), ((0,1,2),(0,2,3)),
                          proof, binding_sha256=revision.dependency_fingerprint)
    return dict(view_set=revision.to_dict(), inputs={view.view_id: base["inputs"][original.view_id] for view in revision.views},
        surface=surface.to_dict(), view_settings={view.view_id: dict(color_space="sRGB",photometry="albedo",
            verified=True,evidence=proof.to_dict()) for view in revision.views}, policy={"sampling_size":16})


def check_appearance(value, envelope):
    assert envelope["status"] == envelope["technical_status"] == "completed", envelope
    assert envelope["verification_status"] == value["identity_status"] == "unknown", value
    assert value["deterministic_status"] == "pass", value["report"]
    from meshvenn_engine.core.appearance_diagnostics import AppearanceResult
    strict = dict(value)
    for field in ("verification_status", "identity_status", "deterministic_status"):
        strict.pop(field)
    restored = AppearanceResult.from_dict(strict)
    assert restored.provenance.grid_samples > 0 and restored.pairs
    assert restored.identity_status == "unknown"
    assert restored.semantic is not None and restored.semantic.qualification_evidence is None
    return restored


def check_diagnostic(value, envelope):
    assert envelope["status"] == envelope["technical_status"] == "completed", envelope
    assert envelope["verification_status"] == "pass", envelope
    assert value["volume"]["occupied_count"] > 0
    assert value["provenance"]["termination"] == "exited"
    assert value["attempts"] and value["actual_resolution"] == 16
    from meshvenn_engine.core.geometry_diagnostics import GeometryResult
    strict = dict(value)
    assert strict.pop("verification_status") == "pass"
    restored = GeometryResult.from_dict(strict)
    assert restored.report.verification_status == "pass"
    return restored


def check_mesh(value, envelope, volume, library_sha):
    assert envelope["status"] == envelope["technical_status"] == "completed", envelope
    assert envelope["verification_status"] == "unknown", "Surface extraction cannot certify the asset"
    assert value["mesh"]["vertex_count"] > 0 and value["mesh"]["polygon_count"] > 0
    assert value["provenance"]["source_volume_sha256"] == volume["sha256"]
    assert value["provenance"]["native_library_sha256"] == library_sha
    assert value["provenance"]["isolation"] == "subprocess"
    assert value["provenance"]["worker_pid"] != os.getpid()


async def protocol(args, arguments, volume, library_sha):
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    server = StdioServerParameters(command=sys.executable, args=["-I", "-m",
        "meshvenn_agent.adapters.mcp", "--workspace", str(args.output / "mcp-workspace"),
        "--native-library", str(args.native_library), "--python-executable", sys.executable])
    async with asyncio.timeout(120):
        async with Client(server, read_timeout_seconds=30) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {"meshvenn_capabilities", "meshvenn_preflight", "meshvenn_diagnose",
                             "meshvenn_mesh", "meshvenn_appearance", "meshvenn_artifact_read"}, names

            async def call(name, value):
                result = await client.call_tool(name, value)
                assert not result.is_error, result
                assert type(result.structured_content) is dict
                return result.structured_content

            async def read_result(reference):
                raw = bytearray()
                while True:
                    part = await call("meshvenn_artifact_read", {"sha256": reference["sha256"],
                        "offset": len(raw), "limit": 65536})
                    assert part["status"] == "completed"
                    chunk = base64.b64decode(part["data_base64"], validate=True)
                    assert part["offset"] == len(raw) and part["bytes"] == len(chunk)
                    assert part["total_bytes"] == reference["bytes"]
                    raw.extend(chunk)
                    if part["eof"]:
                        break
                    assert chunk
                assert len(raw) == reference["bytes"]
                assert hashlib.sha256(raw).hexdigest() == reference["sha256"]
                return json.loads(raw)

            caps = await call("meshvenn_capabilities", {})
            assert caps["status"] == "completed"
            invalid = await call("meshvenn_diagnose", {"arguments": {"native_library": "not-an-agent-option"}})
            assert invalid["status"] == "invalid_request", invalid
            preflight = await call("meshvenn_preflight", {"arguments": dict(arguments,
                policy={"required_cameras": []})})
            assert preflight["status"] == "completed"
            diagnostic = await call("meshvenn_diagnose", {"arguments": dict(arguments,
                policy={"resolution": 16, "reprojection_size": 64, "max_seconds": 15})})
            # Exercise the remote chunk API rather than trusting an inline copy.
            restored = check_diagnostic(await read_result(diagnostic["artifact"]), diagnostic)
            assert restored.volume.sha256 == volume["sha256"]
            mesh = await call("meshvenn_mesh", {"arguments": {"volume": volume, "mesh_mode": "surface-nets"}})
            check_mesh(await read_result(mesh["artifact"]), mesh, volume, library_sha)
            appearance = await call("meshvenn_appearance", {"arguments": appearance_arguments()})
            check_appearance(await read_result(appearance["artifact"]), appearance)
            return {"protocol_version": client.protocol_version, "tools": sorted(names),
                    "capabilities": caps, "preflight": preflight, "diagnostic": diagnostic, "mesh": mesh, "appearance": appearance,
                    "native_library_sha256": library_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-library", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.native_library = args.native_library.resolve(strict=True)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    import meshvenn_engine
    import meshvenn_agent
    from meshvenn_engine import MeshvennEngine
    from meshvenn_agent import Gateway, ArtifactStore
    installed = Path(sysconfig.get_paths()["purelib"]).resolve()
    for module in (meshvenn_engine, meshvenn_agent):
        assert Path(module.__file__).resolve().is_relative_to(installed), module.__file__
    assert "bpy" not in sys.modules and "mcp" not in sys.modules
    library_sha = hashlib.sha256(args.native_library.read_bytes()).hexdigest()
    gateway = Gateway(MeshvennEngine(native_library=args.native_library, python_executable=sys.executable),
                      ArtifactStore(args.output / "direct-workspace"))
    catalogue = gateway.catalogue()
    assert {action["name"] for action in catalogue["actions"]} == {
        "engine.capabilities", "views.preflight", "geometry.diagnose", "geometry.mesh", "appearance.diagnose"}
    arguments = source_arguments()
    preflight = gateway.execute("views.preflight", dict(arguments, policy={"required_cameras": []}))
    assert preflight["status"] == "completed"
    assert preflight["verification_status"] == "unknown", "Missing independent alignment anchor stays unknown"
    diagnostic = gateway.execute("geometry.diagnose", dict(arguments,
        policy={"resolution": 16, "reprojection_size": 64, "max_seconds": 15}))
    value = complete_artifact(gateway.read_artifact, diagnostic["artifact"])
    restored = check_diagnostic(value, diagnostic)
    assert restored.provenance.library_sha256 == library_sha
    mesh = gateway.execute("geometry.mesh", {"volume": value["volume"], "mesh_mode": "surface-nets"})
    mesh_value = complete_artifact(gateway.read_artifact, mesh["artifact"])
    check_mesh(mesh_value, mesh, value["volume"], library_sha)
    appearance = gateway.execute("appearance.diagnose", appearance_arguments())
    check_appearance(complete_artifact(gateway.read_artifact, appearance["artifact"]), appearance)
    cancelled = gateway.execute("geometry.diagnose", arguments, cancel=lambda: True)
    assert cancelled["status"] == "cancelled" and cancelled["verification_status"] != "pass"
    assert "bpy" not in sys.modules and "mcp" not in sys.modules
    evidence = {"schema_version": 1, "engine_version": importlib.metadata.version("meshvenn-engine"),
        "agent_version": importlib.metadata.version("meshvenn-agent"), "python": sys.version,
        "mcp_version": importlib.metadata.version("mcp"),
        "engine_source_sha256": installed_source_hash(meshvenn_engine),
        "agent_source_sha256": installed_source_hash(meshvenn_agent),
        "native_library_sha256": library_sha, "engine_path": meshvenn_engine.__file__,
        "agent_path": meshvenn_agent.__file__, "request_sha256": hashlib.sha256(encoded(arguments)).hexdigest(),
        "direct": {"catalogue": catalogue, "preflight": preflight, "diagnostic": diagnostic, "mesh": mesh, "appearance": appearance},
        "mcp": asyncio.run(protocol(args, arguments, value["volume"], library_sha)),
        "scope": "Installed API, MCP transport and actual native execution; not identity, topology or GLB certification"}
    (args.output / "qualification.json").write_bytes(encoded(evidence))
    print("INSTALLED_ENGINE_AGENT_PASS: two installed wheels, strict D3/D4 reports, native mesh, visible appearance, CAS, cancellation and real MCP stdio")


if __name__ == "__main__":
    main()
