# Meshvenn Engine library

`meshvenn-engine` is an installable, provider-independent Python distribution
(Python 3.11+). It exposes the existing D1/D2/D3 engines and native surface
extraction without importing Blender or an agent SDK. The library does not
advertise Blender pipeline execution, rigging, animation, appearance identity or
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
                        python_executable=trusted_cpython_path)
catalogue = engine.capabilities()
result = engine.execute("geometry.diagnose", arguments, cancel=is_cancelled)
```

Capabilities have `schema_version: 1`, `engine_version` and an `actions` mapping.
Each real action declares `version: 1`, availability, reason and JSON input/output
schemas. Configured native availability means the runtime files are present;
the isolated worker validates ABI 1 when executed. The constructor is the only
place to configure binary and interpreter paths. Action arguments cannot select
paths, commands, Python code or providers.

Actions and exact arguments:

| Action | Arguments | Result |
| --- | --- | --- |
| `engine.capabilities` | `{}` | Same catalogue as `capabilities()` |
| `views.preflight` | `view_set`, `inputs`, optional `policy`, `anchors`, empty `regions` | Existing D1 report and D2 alignment proposals |
| `geometry.diagnose` | `view_set`, `inputs`, optional `policy`, `regions` | Existing full D3 result, including preserved adaptive attempts |
| `geometry.mesh` | Strict D3 `volume`, optional `voxel_size`, `center_xy`, `mesh_mode`, `max_seconds` | Native mesh arrays, projection space and runtime provenance |

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
