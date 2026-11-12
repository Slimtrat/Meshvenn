"""Real SDK 2 protocol tests. The protocol fixture never qualifies engine quality."""

import asyncio
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from meshvenn_agent.adapters import mcp as adapter

try:
    SDK_AVAILABLE = importlib.metadata.version("mcp").split(".", 1)[0] == "2"
except importlib.metadata.PackageNotFoundError:
    SDK_AVAILABLE = False

if SDK_AVAILABLE:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters


class ProtocolGateway:
    """Transport specimen only: no reconstruction, validation or quality claims."""

    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def execute(self, action, arguments, *, request_id=None, cancel=None):
        self.calls.append((action, arguments, request_id))
        if arguments.get("wait_for_cancel"):
            self.started.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if cancel is not None and cancel():
                    self.cancelled.set()
                    break
                time.sleep(.01)
        invalid = arguments.get("specimen_invalid") is True
        return {"schema_version": 1, "request_id": request_id or "protocol-specimen", "action": action,
                "action_version": 1, "status": "invalid_request" if invalid else "completed",
                "technical_status": "not_started" if invalid else "completed", "verification_status": "unknown",
                "result": {"received": arguments}, "report": None, "summary": {}, "artifact": None,
                "error": {"code": "specimen", "message": "Transport fixture error", "details": {}} if invalid else None}

    def read_artifact(self, sha256, *, offset=0, limit=65536):
        self.calls.append(("artifact.read", sha256, offset, limit))
        return {"schema_version": 1, "status": "completed", "sha256": sha256, "offset": offset,
                "bytes": 3, "total_bytes": 3, "eof": True, "data_base64": "YWJj", "error": None}


class MCPOptionalDependencyTests(unittest.TestCase):
    def test_missing_sdk_has_actionable_optional_extra_error(self):
        with patch.object(adapter.metadata, "version", side_effect=importlib.metadata.PackageNotFoundError):
            with self.assertRaisesRegex(adapter.MissingMCPDependency, r"meshvenn-agent\[mcp\]"):
                adapter.create_server(ProtocolGateway())

    def test_sdk_one_is_rejected_instead_of_using_obsolete_api(self):
        with patch.object(adapter.metadata, "version", return_value="1.26.0"):
            with self.assertRaisesRegex(adapter.MissingMCPDependency, "SDK 2"):
                adapter.create_server(ProtocolGateway())

    def test_import_does_not_load_sdk_or_engine(self):
        code = (
            "import sys;sys.path.insert(0,sys.argv[1]);"
            "import meshvenn_agent.adapters.mcp;"
            "assert not any(n=='mcp' or n.startswith('mcp.') for n in sys.modules);"
            "assert not any(n=='meshvenn_engine' or n.startswith('meshvenn_engine.') for n in sys.modules);"
            "assert 'bpy' not in sys.modules"
        )
        child = subprocess.run([sys.executable, "-I", "-c", code, str(SOURCE)], capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_trusted_environment_and_flags_are_process_configuration(self):
        parser = adapter.argument_parser({"MESHVENN_WORKSPACE": "work", "MESHVENN_NATIVE_LIBRARY": "core.dll",
                                          "MESHVENN_PYTHON_EXECUTABLE": "python-worker"})
        options = parser.parse_args(["--workspace", "override"])
        self.assertEqual(options.workspace, Path("override"))
        self.assertEqual(options.native_library, Path("core.dll"))
        self.assertEqual(options.python_executable, Path("python-worker"))


@unittest.skipUnless(SDK_AVAILABLE, "Install meshvenn-agent[mcp] with official SDK 2 to run protocol tests")
class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def stdio_parameters():
        bootstrap = (
            "import sys;sys.path[:0]=sys.argv[1:3];"
            "from test_mcp import ProtocolGateway;"
            "from meshvenn_agent.adapters.mcp import create_server;"
            "create_server(ProtocolGateway()).run(transport='stdio')"
        )
        return StdioServerParameters(command=sys.executable,
            args=["-I", "-c", bootstrap, str(SOURCE), str(Path(__file__).parent)])

    async def test_real_stdio_discovery_and_gateway_dispatch(self):
        # The SDK launches a real subprocess and negotiates the actual MCP wire
        # protocol. Only the application fixture is fake, never an engine claim.
        async with Client(self.stdio_parameters(), read_timeout_seconds=15) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual({tool.name for tool in tools}, {"meshvenn_capabilities", "meshvenn_preflight",
                "meshvenn_diagnose", "meshvenn_mesh", "meshvenn_appearance", "meshvenn_artifact_read"})
            for tool in tools:
                properties = tool.input_schema.get("properties", {})
                self.assertFalse({"workspace", "native_library", "python_executable"} & set(properties))
            capabilities = await client.call_tool("meshvenn_capabilities", {})
            self.assertEqual(capabilities.structured_content["action"], "engine.capabilities")
            self.assertEqual(capabilities.structured_content["verification_status"], "unknown")
            for name, action in (("meshvenn_preflight", "views.preflight"), ("meshvenn_diagnose", "geometry.diagnose"),
                                 ("meshvenn_mesh", "geometry.mesh"), ("meshvenn_appearance", "appearance.diagnose")):
                result = await client.call_tool(name, {"arguments": {"opaque": [1, False, None]}, "request_id": "wire-1"})
                self.assertEqual(result.structured_content["action"], action)
                self.assertEqual(result.structured_content["request_id"], "wire-1")
                self.assertEqual(result.structured_content["result"]["received"], {"opaque": [1, False, None]})
            invalid = await client.call_tool("meshvenn_preflight", {"arguments": {"specimen_invalid": True}})
            self.assertEqual(invalid.structured_content["status"], "invalid_request")
            self.assertEqual(invalid.structured_content["technical_status"], "not_started")
            artifact = await client.call_tool("meshvenn_artifact_read", {"sha256": "a" * 64, "offset": 0, "limit": 3})
            self.assertEqual(artifact.structured_content["data_base64"], "YWJj")
            self.assertEqual(artifact.structured_content["sha256"], "a" * 64)
            strict = await client.call_tool("meshvenn_artifact_read", {"sha256": "a" * 64, "offset": "0"})
            self.assertTrue(strict.is_error)

    async def test_real_stdio_legacy_negotiates_tools_and_capabilities(self):
        # This is a real SDK 2 legacy connection to a subprocess. The fake
        # application qualifies adapter compatibility, never engine fidelity.
        async with Client(self.stdio_parameters(), mode="legacy", read_timeout_seconds=15) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual({tool.name for tool in tools}, {"meshvenn_capabilities", "meshvenn_preflight",
                "meshvenn_diagnose", "meshvenn_mesh", "meshvenn_appearance", "meshvenn_artifact_read"})
            result = await client.call_tool("meshvenn_capabilities", {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["action"], "engine.capabilities")
            self.assertEqual(result.structured_content["status"], "completed")
            self.assertEqual(result.structured_content["verification_status"], "unknown")

    async def test_cancel_is_forwarded_to_gateway_work_in_sdk_thread(self):
        import anyio
        gateway = ProtocolGateway()
        async with Client(adapter.create_server(gateway), raise_exceptions=True, read_timeout_seconds=15) as client:
            state = {}
            done = anyio.Event()

            async def request():
                with anyio.CancelScope() as scope:
                    state["scope"] = scope
                    try:
                        await client.call_tool("meshvenn_diagnose", {"arguments": {"wait_for_cancel": True}})
                    finally:
                        done.set()

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(request)
                self.assertTrue(await anyio.to_thread.run_sync(gateway.started.wait, 2))
                state["scope"].cancel()
                with anyio.fail_after(3):
                    await done.wait()
                self.assertTrue(await anyio.to_thread.run_sync(gateway.cancelled.wait, 2))


if __name__ == "__main__":
    unittest.main()
