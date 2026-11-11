# meshvenn-agent

Provider-neutral, versioned action gateway for Meshvenn. The base distribution
requires only Python 3.11+ and its standard library. Importing `meshvenn_agent`
does not import Blender, `core`, a native engine, a model/provider SDK or MCP.
`EnginePort` is the only engine dependency; the separate `meshvenn-engine`
distribution implements it. The MCP transport is an optional adapter.

```python
from pathlib import Path
from meshvenn_engine import MeshvennEngine
from meshvenn_agent import ArtifactStore, Gateway

# These paths are trusted host configuration, never agent action arguments.
engine = MeshvennEngine(native_library=trusted_library,
                       python_executable=trusted_python)
gateway = Gateway(engine, ArtifactStore(workspace=Path("/host/workspace")))
catalogue = gateway.catalogue()
reply = gateway.execute("geometry.diagnose", {
    "view_set": view_set_json, "inputs": original_raster_dtos,
}, request_id="diagnostic-001", cancel=is_cancelled)
```

`catalogue()` returns `schema_version: 1`, gateway/engine versions, and an action
list containing `name`, `version`, availability/reason, JSON input/output schemas
and capability annotations. Supported actions are `engine.capabilities`,
`views.preflight`, `geometry.diagnose` and `geometry.mesh`. The engine supplies
the complete input schemas and validates its D1/D2/D3 semantic contracts. The
gateway additionally rejects unknown actions/versions/arguments, host paths,
backend/trust overrides and nonfinite or over-budget JSON. PNG inputs are encoded
bytes; decoded RGBA DTOs contain explicit dimensions and normalized values. An
agent cannot select arbitrary filesystem paths or override the configured engine.
Camera verification and canonical evidence remain producer declarations under
the engine's contracts; this gateway does not calibrate cameras or certify them.

`invoke()` accepts exactly `{schema_version: 1, request_id, action,
action_version: 1, arguments}`. `invoke_json()` additionally rejects duplicate
JSON keys and malformed UTF-8. Calls return a JSON envelope with `status`,
`technical_status`, `verification_status`, bounded `result`/`report`/`summary`, an
immutable `artifact` reference and a structured `error` or `null`. Expected error
statuses are `invalid_request`, `unavailable`, `cancelled` and `failed`; specific
engine codes such as `stale_source` remain visible. A successful call means that
the operation returned. It does not establish geometric quality. Verification
comes only from the engine's explicit derived status; successful mesh construction
remains unknown. The gateway never reconstructs the D1 verification decision from
finding means, labels or successful execution.

Full returned JSON is stored losslessly by SHA-256, including partial evidence
returned during cancellation. If it exceeds the inline limit, `result` is `null`;
use the artifact rather than assuming the summary contains the full geometry.
Large diagnostic reports are retained in that JSON instead of being presented
as incomplete D1 reports. A cancellation callback is passed unchanged to the
engine; post-return cancellation retains the returned artifact and uses cancelled
technical status with unknown verification.

`ArtifactStore(workspace=...)` writes only beneath that trusted workspace's
`artifacts/<prefix>/<sha256>` directories. Publication is atomic and never replaces
an existing accepted address. Existing corruption is rejected rather than repaired
silently. Files, shard directories and the store root must not be symlinks or
Windows reparse points. The workspace is host-owned; an agent cannot choose it.
SHA-256 is checked at publication and on every read, using a fixed byte-count
budget and the same open file for verification and chunk retrieval. Metadata is
checked around both operations; nonregular files are rejected before opening. The store does not
claim to defend against a hostile owner controlling the trusted workspace itself.

`read_artifact(sha256, offset=0, limit=65536)` returns bounded base64 chunks:
`{schema_version, status, sha256, offset, bytes, total_bytes, next_offset, eof,
data_base64, error}`. Only lowercase SHA-256 addresses are accepted, never paths or
artifact URIs as input. The reference contains `{sha256, bytes, media_type, uri}`;
URIs have the form `meshvenn-artifact://<sha256>`. JSON results use
`application/json`. Integer offsets and limits are checked before reading.

Default limits are 64 MiB requests, 256 MiB responses/artifacts, 16 KiB inline
results, 12 KiB embedded reports, 64 KiB chunks, depth 32 and 20 million JSON
nodes. Hosts can configure stricter `GatewayLimits` and store limits. No shell,
code execution endpoint or paid provider call is exposed.

```sh
python -m pip install -e packages/meshvenn_agent
python -m unittest discover -s packages/meshvenn_agent/tests -p 'test_gateway*.py'
python -m pip install 'meshvenn-agent[mcp]'
meshvenn-mcp --workspace /host/workspace
```

The optional `mcp>=2,<3` extra provides the MCP adapter's dependency and
`meshvenn-mcp` entry point. Fake-port tests qualify the adapter and storage only;
they are not geometric evidence. Native installed-wheel/MCP integration is
validated separately against a real engine and native library.
