"""Official MCP SDK 2 stdio adapter. All application work belongs to Gateway.

Importing this module does not import MCP, anyio, the engine, core or Blender.
The optional SDK and engine facade are loaded only when explicitly requested.
"""

import argparse
from importlib import metadata
import os
from pathlib import Path
import sys
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from meshvenn_agent import Gateway


class MissingMCPDependency(RuntimeError):
    """The optional official MCP SDK 2 distribution is unavailable."""


def _load_sdk():
    try:
        version = metadata.version("mcp")
        if version.split(".", 1)[0] != "2":
            raise MissingMCPDependency(
                "Meshvenn MCP requires official SDK 2 (mcp>=2,<3). "
                "Install meshvenn-agent[mcp] in this Python environment."
            )
        from mcp.server import MCPServer
        import anyio
        from pydantic import StrictInt, StrictStr
    except (metadata.PackageNotFoundError, ImportError) as exc:
        raise MissingMCPDependency(
            "The optional MCP SDK is missing. Install meshvenn-agent[mcp] "
            "(official mcp>=2,<3) in this Python environment."
        ) from exc
    return MCPServer, anyio, StrictInt, StrictStr


def create_server(gateway: "Gateway"):
    """Wrap one configured Gateway; no backend configuration enters tool args."""
    MCPServer, anyio, StrictInt, StrictStr = _load_sdk()
    server = MCPServer(
        "Meshvenn Agent", version="0.1.0", log_level="WARNING",
        instructions=(
            "Read meshvenn_capabilities before choosing an action. "
            "Tool results preserve Gateway status, technical_status and verification_status: "
            "technical completion does not establish visual quality. "
            "Backend paths and workspace are configured by the process owner, never tool arguments. "
            "Read large results by their SHA-256 artifact reference."
        ),
    )

    def cancellation_check():
        # MCP SDK 2 runs ordinary def tools in an anyio worker thread. Resolve
        # its backend cancellation type on that thread's owning event loop.
        cancelled_type = anyio.from_thread.run_sync(anyio.get_cancelled_exc_class)

        def cancelled():
            try:
                anyio.from_thread.check_cancelled()
            except cancelled_type:
                return True
            return False
        return cancelled

    @server.tool()
    def meshvenn_capabilities() -> dict[str, Any]:
        """Return actual engine capabilities in the shared Gateway result envelope."""
        return gateway.execute("engine.capabilities", {}, cancel=cancellation_check())

    @server.tool()
    def meshvenn_preflight(arguments: dict[str, Any], request_id: StrictStr | None = None) -> dict[str, Any]:
        """Run views.preflight with its versioned JSON arguments; inspect verification_status."""
        return gateway.execute("views.preflight", arguments, request_id=request_id, cancel=cancellation_check())

    @server.tool()
    def meshvenn_diagnose(arguments: dict[str, Any], request_id: StrictStr | None = None) -> dict[str, Any]:
        """Run bounded real geometry.diagnose; silhouette consistency does not certify hidden surfaces."""
        return gateway.execute("geometry.diagnose", arguments, request_id=request_id, cancel=cancellation_check())

    @server.tool()
    def meshvenn_mesh(arguments: dict[str, Any], request_id: StrictStr | None = None) -> dict[str, Any]:
        """Run bounded geometry.mesh from a validated volume; completion alone is not asset acceptance."""
        return gateway.execute("geometry.mesh", arguments, request_id=request_id, cancel=cancellation_check())

    @server.tool()
    def meshvenn_appearance(arguments: dict[str, Any], request_id: StrictStr | None = None) -> dict[str, Any]:
        """Run appearance.diagnose on bounded visible source regions; optional model judgments do not certify identity, geometry or export."""
        return gateway.execute("appearance.diagnose", arguments, request_id=request_id, cancel=cancellation_check())

    @server.tool()
    def meshvenn_artifact_read(sha256: StrictStr, offset: StrictInt = 0, limit: StrictInt = 65536) -> dict[str, Any]:
        """Read a verified bounded base64 chunk from the configured artifact store by content hash."""
        return gateway.read_artifact(sha256, offset=offset, limit=limit)

    return server


def build_gateway(*, workspace: Path, native_library: Path | None = None, python_executable: Path | None = None):
    """Trusted process bootstrap; the adapter knows only public package facades."""
    from meshvenn_agent import ArtifactStore, Gateway
    from meshvenn_engine import MeshvennEngine
    engine = MeshvennEngine(native_library=native_library, python_executable=python_executable)
    return Gateway(engine, ArtifactStore(workspace=workspace))


def argument_parser(environ=None):
    environment = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=environment.get("MESHVENN_WORKSPACE"),
                        help="Trusted local artifact workspace; or MESHVENN_WORKSPACE.")
    parser.add_argument("--native-library", type=Path, default=environment.get("MESHVENN_NATIVE_LIBRARY"),
                        help="Trusted native library path; or MESHVENN_NATIVE_LIBRARY.")
    parser.add_argument("--python-executable", type=Path, default=environment.get("MESHVENN_PYTHON_EXECUTABLE", sys.executable),
                        help="Trusted native worker CPython; or MESHVENN_PYTHON_EXECUTABLE.")
    return parser


def main(argv=None) -> int:
    parser = argument_parser()
    options = parser.parse_args(argv)
    if options.workspace is None:
        parser.error("--workspace or MESHVENN_WORKSPACE is required")
    try:
        # Report an absent optional extra before attempting the engine bootstrap.
        _load_sdk()
        gateway = build_gateway(workspace=options.workspace, native_library=options.native_library,
                                python_executable=options.python_executable)
        create_server(gateway).run(transport="stdio")
    except (MissingMCPDependency, ImportError, OSError, ValueError) as exc:
        print(f"Meshvenn MCP could not start: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
