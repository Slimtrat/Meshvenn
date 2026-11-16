# Meshvenn Engine library

`meshvenn-engine` is an installable, provider-independent Python distribution
(Python 3.11+). It exposes the existing D1/D2/D3/D4/D5/D6 engines and native surface
extraction without importing Blender or an agent SDK. The library does not
advertise Blender pipeline execution, rigging, animation, unqualified appearance identity or
export certification.

The existing `core/` files remain the source of truth. Setuptools maps their
pure dependency closure to `meshvenn_engine.core`; Blender keeps its current
`core` imports. No copied engine implementation is maintained. The wheel excludes
Blender-dependent material/image/mesh adapters, UI, operators and agent code.
Neither a native binary nor CPython is bundled. A trusted host supplies these
runtime dependencies; installing the wheel alone still supports preflight.

Build with `python -m build --sdist --wheel --outdir dist/engine .`.
The sdist contains the complete selected core sources and builds its wheel
independently of the repository. For development, adding `lib/` to Python's
search path applies the same source mapping; installed wheels do not search a
checkout.

```python
from meshvenn_engine import EngineError, MeshvennEngine

engine = MeshvennEngine(native_library=trusted_native_path,
                        python_executable=trusted_cpython_path,
                        loop_workspace=trusted_loop_workspace)
catalogue = engine.capabilities()
result = engine.execute("geometry.diagnose", arguments, cancel=is_cancelled)
```

Capabilities have `schema_version: 1`, `engine_version` and an `actions` mapping.
Each real action declares `version: 1`, availability, reason and JSON input/output
schemas. Configured native availability means the runtime files are present;
the isolated worker validates ABI 1 when executed. The constructor is the only
place to configure binary and interpreter paths. Action arguments cannot select
paths, commands, Python code or executable providers. Planning accepts declared
provider capabilities as data; those declarations do not configure a connection.

Actions and exact arguments:

| Action | Arguments | Result |
| --- | --- | --- |
| `engine.capabilities` | `{}` | Same catalogue as `capabilities()` |
| `views.preflight` | `view_set`, `inputs`, optional `policy`, `anchors` | Existing D1 report and D2 alignment proposals |
| `geometry.diagnose` | `view_set`, `inputs`, optional `policy`, `regions` | Existing full D3 result, including preserved adaptive attempts |
| `geometry.mesh` | Strict D3 `volume`, optional `voxel_size`, `center_xy`, `mesh_mode`, `max_seconds` | Native mesh arrays, projection space and runtime provenance |
| `appearance.diagnose` | `view_set`, `inputs`; optional `surface`, `view_settings`, `regions`, `region_anchors`, `upstream_reports`, `policy` | Strict D4 visible color/coverage evidence and separate identity assessment |
| `corrections.plan` | `view_set`, `reports`; optional `capabilities`, `annotations`, `policy` | Inspectable D5 correction plans with explicit readiness and current evidence bindings |
| `corrections.prepare` | `plan`, `view_set`, `reports`; optional `capabilities`, `annotations`, `policy` | A revalidated prompt package for one ready regional edit; no generation |
| `corrections.loop` | `operation`, `session_id`; optional operation-specific `payload` | Durable bounded correction orchestration, with separate accepted evidence and unknown asset verification |

Loop operations are `start`, `status`, `advance`, `resume`, `cancel`, `supply`
and `artifact_read`, plus optional artifact preloading with `artifact_put`. The
runtime validates each operation's exact payload.
`MeshvennEngine(..., loop_workspace=trusted_path,
generation_provider=trusted_provider, loop_evaluator=trusted_evaluator)` configures
the optional host ports. These objects, credentials, executable code and storage
paths cannot be supplied through action arguments. Without a loop workspace the
loop action is unavailable; the local diagnostic and planning actions remain
usable. Missing provider or evaluator ports remain explicit in session state and
cannot manufacture a completed correction or accepted diagnostic report.
When no service port is configured, a start payload may declare strict
`ProviderInfo` metadata for `host_tool` execution. This records the host dispatch
mode and explicit request cost ceiling; it supplies no provider object,
credential, calibrated fidelity or invented quota.

Session state is persisted beneath the trusted workspace. Read its bounded
artifacts through the same action's `artifact_read` operation, identified by
content hash; this does not expose arbitrary filesystem reads. `supply` is an
operation validated by the host runtime, never authority for a remote caller to
invent accepted evaluation reports. Every loop response keeps
`verification_status: "unknown"`; inspect the session phase, stopping reason and
actual accepted reports separately. Loop completion does not certify the asset.
State responses include two runtime-derived fields, `known_cost` and
`cost_uncertain`. Remove those two keys before `LoopState.from_dict`; the remaining
state is the strict core snapshot. Gateway summaries preserve these values and
the session state without reconstructing financial or quality decisions.

Correction actions run without a native library, provider SDK or network access.
They accept at most 20 current strict `DiagnosticReport` dictionaries, 20 views
and 128 `EditAnnotation` dictionaries. `ProviderCapabilities` declares supported
request controls, not provider fidelity; omitted capabilities grant no controls.
Annotations use original source coordinates and explicit evidence, with an
optional inline source-frame mask. Unknown fields and host configuration are
rejected through the same strict core DTOs as direct callers.

`corrections.prepare` accepts only an `edit_region` plan whose readiness is
`ready`. It revalidates current revisions, report hashes, policy, annotations and
capabilities, then recomputes the plan before returning its prompt package.
Stale or altered plans fail; preparation never edits a source or calls a provider.
Other action kinds remain inspectable plans for manual work. Readiness describes
whether the proposed request can be prepared, not asset acceptance. Both actions
always return `verification_status: "unknown"`; preserve the core result's
separate readiness and completion fields. Their full dictionaries round-trip
through `CorrectionResult.from_dict` or `PreparedCorrection.from_dict`, including
the fixed unknown verification field.

Appearance runs without a native library. `surface` is a strict `SurfaceMesh`
with declared native-normalized vertices/triangle indices, provenance and optional
view-set binding. `view_settings` maps actual view IDs to `AppearanceViewSettings`
with explicit color encoding, photometry and producer evidence. Regions use D1
original source coordinates; optional `AppearanceRegionAnchor` dictionaries bind
expected parts to authored surface support. `upstream_reports` contains at most
20 strict D1 reports; failed or stale evidence remains failed/unknown.

`MeshvennEngine(..., vision_analyzer=trusted_host_analyzer)` is the only way to
inject optional semantic inference. An action cannot supply a provider, callable
or qualification override. Without qualified host evidence, identity remains
unknown even when visible colors match. Appearance returns three derived fields:
`verification_status`, `identity_status`, and `deterministic_status`. Remove those
three keys before `AppearanceResult.from_dict`; all original typed evidence is
otherwise unchanged. Numerical color agreement does not qualify unseen parts,
identity, geometry or export. The wheel includes pure material visibility helpers
and excludes `material_visibility/blender_backend.py` entirely.

`view_set` and each region use the existing strict D1 dictionaries. `inputs` is
keyed by declared view ID; each entry contains `image` and optional `mask`.
Each raster uses exactly one representation:

* `{"png_base64": "..."}`: original encoded PNG bytes, decoded by the real
  `RasterInput.from_png_bytes`. Optional `format` must equal `"png"`.
* `{"width": 31, "height": 31, "rgba": [...]}`: flat bottom-left-origin straight
  RGBA, finite numbers in `[0,1]`, decoded by `RasterInput.from_pixels`. Optional
  `format` must equal `"rgba"`. The source reference hashes the core's canonical
  decoded buffer, rather than claiming original file provenance.

No arbitrary encoded source override is accepted. PNG, decode, hash, camera,
canonical reference and registration decisions remain in D1/D2. Missing
canonical anchors can correctly leave preflight UNKNOWN. Policies accept their
existing dataclass field names, including `required_cameras: []` for preflight.
There are at most 20 views, 128 regions, 1 Mi-pixel per raster, 4 Mi-pixels of
aggregate decoded rasters and 64 MiB of encoded JSON per request.

Preflight and geometry results expose `verification_status` derived exclusively
from `report.verification_status`. For geometry this is the sole additional
field on the strict D3 dictionary; remove it before calling
`GeometryResult.from_dict`. Native cancelled/partial reports retain their
attempt artifacts instead of being discarded by the facade. Technical success
does not constitute asset acceptance.

Mesh extraction uses `NativeCore.build_surface_mesh` in a killable CPython
subprocess, never a second geometry algorithm. Defaults are `voxel_size: 1`,
`center_xy: true`, `mesh_mode: "blocks"`, `max_seconds: 30`. The other supported
mode is `"surface-nets"`. Time is bounded to 120 seconds, exposed cell faces to
65,536, vertices to 262,144, indices to 1,048,576 and response JSON to 32 MiB.
Mesh arrays are flat `vertices` XYZ floats, `indices` integers, and explicit
`polygon_starts`/`polygon_sizes`. A mesh result always has quality
`verification_status: "unknown"`; no topology or export certification is implied.

`EngineError` exposes stable `code`, `message`, `details` and `to_dict()`. Codes
include `unknown_action`, `invalid_arguments`, `cancelled`, `timeout`,
`host_unavailable`, `native_unavailable`, `native_failure`, and `resource_limit`.
D1/D2/D3 findings remain successful transport results even when their measured
quality is FAIL/UNKNOWN; adapters must preserve their reports and artifacts.

Validation:

* `python -m unittest tests.test_engine_library -v` runs facade contracts; set
  `MESHVENN_TEST_NATIVE_LIBRARY` to run the real native diagnostic/mesh tests.
* With setuptools and wheel installed, set
  `MESHVENN_TEST_ENGINE_PACKAGING=1` and run
  `python -m unittest tests.test_engine_library_packaging -v`. It builds an sdist,
  rebuilds a wheel from that sdist outside the checkout, audits the pure source
  closure, installs without network, and executes CPython `-I` from a temporary
  working directory. With the native variable set, both the installed D3 worker
  and mesh worker must execute successfully. Packaging opt-in fails if build
  dependencies are missing; the ordinary stdlib test suite does not require them.

The repository's [D7 evidence command](diagnostic-evidence.md) replays frozen
diagnostic corpora and archived real-tool output outside this library. Its
offline comparison/review page records failures and unknowns; it does not add
provider credentials, host tools or quality claims to the pure engine.
