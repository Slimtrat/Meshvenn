# Static orthographic geometry diagnostics (D3 / #80)

`core.geometry_diagnostics` is a read-only diagnostic engine using the existing
`NativeCore` visual-hull implementation. It does not modify images, choose a
replacement view, generate content or certify hidden concavities, topology,
appearance, anatomy, animation or GLB delivery.

```python
from pathlib import Path
from core.geometry_diagnostics import (
    GeometryPolicy, GeometryResult, NativeGeometryBackend, analyze_geometry,
)

# view_set is the immutable D1 ViewSetRevision. inputs maps its stable IDs to
# D2 ViewInput objects containing original, decoded color and subject masks.
backend = NativeGeometryBackend(
    library_path=Path("/absolute/path/to/bpt_core.dll"),
    python_executable=Path("/absolute/path/to/python.exe"),
)
result = analyze_geometry(view_set, inputs, backend=backend,
                          policy=GeometryPolicy(resolution=32), regions=important_regions)
report_json = result.report.to_json()
saved_artifacts = result.to_json()
restored = GeometryResult.from_json(saved_artifacts)
```

In ordinary Python, the backend can discover the installed library and use
`sys.executable`. Blender must supply a separate CPython executable explicitly;
the Blender binary is not a Python CLI. Missing hosts, missing binaries, DLL load
or execution errors and crashed workers retain structured unknown findings.
The add-on/service host owns how that Python worker is provisioned. No additional
native algorithm, network service or third-party Python dependency is introduced.

## Measurement and source authority

The engine reruns D2 against actual immutable buffers before using any source.
Original hashes, dimensions, normalized values, masks/alpha and supported verified
orthographic camera declarations are checked. D2's lack of an independent
alignment anchor remains visible as optional unknown information; it does not
block measurement of calibrated cross-view disagreements. A verification flag
and its hashed producer evidence are assumptions, not calibration performed here.

Declared `ProjectionAlignment` is applied once with the existing shared mapping,
before camera Flip X. Complete aligned source masks up to 1,048,576 pixels drive
native reconstruction. The measurement grid preserves aspect ratio and is bounded
by 256 pixels per axis by default. Nearest-neighbor endpoint sampling, original
and decoded hashes, aligned hashes, source dimensions and measurement dimensions
are retained; the original revision and source content are never resized or
rewritten. Callers can supply named normalized bottom-left `Region` bounds.

Per-view artifacts include expected/reprojected silhouettes, missing/extraneous
maps, IoU, precision/recall, symmetric contour mean/max distances in measurement
pixels, connected residual regions and every expected connected component up to
the explicit count budget. Named regions and components are evaluated separately
from the global mean. A missing detached part can therefore fail with high IoU.
Regions below raster/voxel support, regions without expected foreground, lost
source components during reduction and truncated component lists remain required
unknowns. An unannotated semantic detail inside a large connected component is
not certified by its component mean. Add an important region for that constraint.

Geometric compatibility and physical detail resolution are separate observations.
Nonempty silhouettes can agree within the derived symmetric foreground-distance
tolerance when expected and projected components correspond one to one, even if
conservative voxel cells lower raw IoU. Raw IoU and all residual counts remain
unchanged in the artifacts. This compatibility finding does not resolve a small
physical feature. `geometry.sampled_component_coverage` is a separate optional
observation: a pass requires every expected pixel to be present and an isolated
one-to-one actual component. A merge, split or a deficit within uncertainty does
not qualify for that pass. Required physical/important-region uncertainty remains
visible and cannot be overruled by sampled coverage or a high mean score.

Exact antipodal declarations `(azimuth + 180, -elevation)` also permit direct
silhouette comparison: horizontal coordinates reflect and vertical coordinates
agree before the declared Flip X. This check uses the shared camera transform,
the same original raster dimensions and an explicit half-pixel measurement
tolerance by default. It has no voxel uncertainty. Different original grids
remain unknown in this direct comparison profile. Actual pair masks, residuals,
regions and mapping are retained in `result.pair_comparisons`. Pair evidence can
establish a small local source contradiction while the coarse native ROI remains
unknown; those two observations are retained separately and neither identifies
the true source without independent evidence.

The [numerical convention](geometry-diagnostic-numerics.md) documents finite-cell
reprojection, native coordinate authority and resolution uncertainty. Raster
differences wholly explained by the supported resolution do not establish a
cross-view contradiction. Undefined contour distance for empty/nonempty masks is
`null`, not zero.

## Counterfactuals and attribution

Native sessions reconstruct the canonical sorted full set and every set excluding
one observation. One-view sessions are valid counterfactuals; one view or only
parallel/opposed viewing axes cannot earn full 3D qualification. Reference/control
views never supply observation coverage. Every experiment retains included and
excluded IDs, immutable volume, per-view reprojections and elapsed native time.

A separate acquisition-order trace preserves occupancy before/after every source.
Its final volume is checked against canonical order. Reductions and the last view
are execution provenance, never a blame ranking. Final measurements use sorted
stable IDs, so source permutation cannot change conclusions.

Conflicts produce a suspect constraint group with `geometry.attribution=unknown`.
An excluded-view residual alone does not identify the correct image. A useful view
may remove most of a valid hull. Same-camera canonical reference comparisons can
support a particular observation or identify a mismatch only when the canonical
reference is validated with hashed evidence, reference inputs/cameras are usable,
and direct/transitive source lineage is independent of the target. Shared source
bytes or ancestry cannot arbitrate their own descendants. Canonical sampling loss
also remains unknown. No automatic deletion or regeneration action is applied.

## Bounds, cancellation and provenance

Default requested native resolution is 32; the supported range is 8–64. Optional
adaptive refinement is enabled by default and permits one additional attempt at
64 when the first grid is empty or required native detail remains unresolved.
It does not retry known direct-pair/canonical conflicts or invalid inputs, does
not recurse and never runs more than two resolutions. Disable it explicitly with
`GeometryPolicy(adaptive_refinement=False)`. Resolution limits, thresholds and
the original policy hash stay fixed throughout the request.

`result.requested_resolution` records the initial request;
`result.actual_resolution` records the final attempt. `result.attempts` preserves
each `GeometryAttempt`, including its report, volume, view metrics, experiments,
trace, pair artifacts and execution provenance. The initial empty/unknown outcome
is retained even when the finer grid resolves it. A failed, timed-out or cancelled
second attempt stays unknown and keeps the first attempt intact. Reaching the
native resolution ceiling does not make unresolved physical parts pass.

At most 10 usable observations, 20 total snapshot views, 12 native sessions per
attempt, 24 sessions total, 220 native projection applications and 57,671,680
potential voxel tests are accepted. Named/component regions are capped at 128,
threads at eight and the shared deadline at 120 seconds. Defaults are 30 seconds
and one thread. Both attempts consume one shared ledger and the same absolute
deadline; neither resets the remaining budget. The refinement gate conservatively
reserves enough native capacity for either acquisition order.

Projection/metric calls each have an explicit operation cap. A second aggregate
budget reserves their conservative call capacities and bounded source passes,
up to eight billion declared work units. This is a workload reservation, not a
CPU instruction counter. `*_reserved` fields in each attempt are deltas; the final
provenance contains their sums, actual completed native session/application
counts, attempted resolutions and the declared aggregate caps. Identical
volume/view measurements are reused exactly within each attempt.

Each attempt runs its DLL calls in a disposable subprocess, with at most two
sequential subprocesses per request. A deadline or cancellation causes
the parent to terminate it, escalate to kill if needed, and wait for its exit.
This interrupts blocked native calls; it does not pretend that a cooperative
Python check can do so. Native sessions write atomically after completion, so
finished volumes survive interruption. Preparation, source component scans,
reprojection and distance transforms have finite size/work bounds and cooperative
deadline/cancellation checks. Their checks cannot hard-interrupt an arbitrary host
decoder or a cancellation callback. Input decoding occurs before this API.

Malformed input, missing coverage, empty measured hull, unavailable host/library,
native failure, worker failure, work budget, time budget and cancellation have
distinct findings. Incomplete work never passes required checks. A zero-voxel hull
reports its measured outcome; at coarse resolution a thin feature can remain
unresolved, and emptiness alone does not establish which source is wrong.

Both the common `DiagnosticReport` and strict typed result retain engine and
library/source hashes, original policy settings, requested/actual resolutions, sampling assumptions,
experiment artifact hashes, timing and compute bounds. The typed result additionally
contains the full voxel/raster data and source-order trace. Library/source/policy,
camera, alignment, reference or decoded-buffer changes invalidate dependencies.
Source hashes include framed logical paths and bytes for the geometry engine,
native bridge/loader, projection authorities, image masks and shared D1/D2 code.
Timing and acquisition order remain execution provenance rather than truth labels.

Run focused validation with:

```sh
python -m unittest tests.test_geometry_diagnostics tests.test_geometry_diagnostic_projection
```

Real native tests use the installed DLL or `MESHVENN_TEST_NATIVE_LIBRARY` and are
explicitly skipped where no real library exists. Mocked worker deadline tests
verify terminate/reap orchestration only; they are not native quality evidence.
The independent native sampler audit in the numerical test module additionally
uses `MESHVENN_TEST_NATIVE_DLL`; set both variables to the same qualified binary
to run every native check without skips.
