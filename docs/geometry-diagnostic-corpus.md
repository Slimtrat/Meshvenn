# Native D3 diagnostic corpus

`geometry-v1` extends the frozen D1/D2 corpus without changing its labels,
thresholds or original assets. It exercises the real `NativeCore` visual hull
through the isolated `core.geometry_diagnostics` worker, reprojects actual
occupied voxels, and records leave-one-out experiments. It is an initial D7
qualification tranche for #80/#84; #84 remains open.

The [measured development record](geometry-diagnostic-corpus-baseline.json)
retains the complete first attempt's hashes, assertions, failures, abstentions,
experiments and latency. It evaluated 57 configurations/orders in 88.19 seconds:
44 passed their initial evaluator and 13 failed. All 22 order comparisons
passed, with no unexpected execution exceptions. This is a **failed full
qualification**, preserved for review rather than hidden by a later fix.

The first native binary SHA-256 was `2dc0da20ba8b5d5366cb8d24f35ab0c3d5870de72f2189a95630f1a38843bb5e`;
that existing local binary is not asserted to be the exact PR #86 CI build.
The first evaluator also accepted one passing healthy view while other views
could be unknown, and compared exact regional bounds across resolutions.
Both evaluator limitations are identified in the record; subsequent attempts
require a measured pass for every healthy observation and compare regional
labels/statuses separately from changing pixel bounds.

The initial source at 32 voxels produced an empty volume for the valid thin
shape. At 48 voxels its valid right view removed 32,496 to 1,354 voxels (95.83%)
without establishing fault; side detail still remained unknown. The small
flag at `(128,48)` had mean native IoU 0.91025 while its named back region had
recall 0.125 and failed. Coarser regional abstentions remain visible. An
independent canonical comparison initially missed an extended appendage despite
the native cross-view conflict; its failed expectation is retained in the
[original report](geometry-diagnostic-corpus-evidence/initial-canonical-conflict/diagnostic-report.json).

The corrected evaluation uses the exact PR #86 CI Windows binary, SHA-256
`d6803649c54c6d16128541a1fb7edfdecc4dfcaab3594cddeb838db86950d2c8`.
Its complete matrix took 75.52 seconds: 49 of 57 evaluations satisfied the
frozen expectations, with zero unexpected execution exceptions. All 22 order
checks and 22 matched regional localization checks passed their declared
tolerances. Seventeen of 22 resolution comparisons retained the same
classifications; all actual differences and bounds remain in the record.
The independent canonical and important named-region controls now pass at all
five requested configurations/orders.

**The complete D3 qualification still fails.** Eight frozen evaluations remain
unsatisfied: the five thin-shape variants and the three 64-pixel/32-voxel
heldout-healthy orders. Four thin variants produce an actual empty 32-voxel
volume; the 48-voxel variant retains unknown side detail. Heldout-healthy side
reprojections are unknown at the coarse raster but pass at 128 pixels. These
are resolution limits and unexpected healthy-control abstentions, not evidence
that a source image is faulty. The CLI exits 1 and claims no full qualification.

At coarse resolution, the important flag now has
[actual calibrated antipodal raster evidence](geometry-diagnostic-corpus-evidence/corrected-small-region-coarse/overlay-input-pair-back-front.png)
of a regional mismatch while the native regional measurement remains unknown.
Native voxel evidence and direct input evidence are retained as different
methods; the latter does not pretend the coarse hull resolved the missing part.
The [corrected canonical report](geometry-diagnostic-corpus-evidence/corrected-canonical/diagnostic-report.json)
also records actual independent same-camera comparison masks. The intermediate
duplicate-finding exception exposed by combining native and direct evidence is
preserved in the preceding run rather than removed from the development record.

The 13 original analytic cases and all expectations were committed as
`d51efb6` **before native evaluation**. The manifest SHA-256 is
`aea6c48d9ffdfe1c5777291c4f0c82c945cb6fcd44e9a398fa9790ba9eb47a49`.
The generator reuses the earlier cardinal AABB projection recipe, but has a
separate source/version, boxes, source hashes, labels and asset directory.
Labels or policy thresholds must not be changed to make an observed failure
pass. Reruns after implementation fixes are regression evidence on an exposed
holdout, not fresh statistical validation.

| Cases | Frozen requirement |
| --- | --- |
| Healthy, heldout healthy, intentional asymmetry | Real nonempty reconstruction and measured consistency; no automatic blame |
| Valid informative reduction | Healthy consistency even when a valid view removes at least 90% of remaining voxels; canonical order places that view after another observation |
| Local appendage conflict | Actual cross-view conflict; uncertain fault attribution |
| Ambiguous conflicting pair | Conflict remains ambiguous without independent canonical evidence |
| Independent canonical resolves pair | Same observations plus independently authored reference support localization of the front discrepancy for review |
| Small important region | A named `identity_flag` region fails even when mean view IoU is at least 0.90 |
| Insufficient coverage | Explicit unknown coverage and no blame |
| Empty incompatible views | Valid nonempty original inputs produce an actual empty native volume, distinctly reported |
| Invalid camera | Unsupported camera remains an input/camera result, never a fabricated geometry cause |
| Real worker deadline | Actual bounded isolated-worker deadline; native completion is unknown |
| Real native rejection | Actual DLL `bpt_visual_hull_create` rejects resolution zero in a subprocess with a five-second hard deadline |

The final two cases establish operational paths only. The native rejection
probe invokes the real binary, records its numeric error code, and marks
`geometry_quality_evaluated=false`. The worker deadline can expire before the
DLL call completes or even begins; it does not establish a native crash. Mock
orchestration tests cannot substitute for either record or qualify geometry.

Ground truth is exact mathematical authorship and knowledge of an injected
silhouette defect. This is synthetic truth, not a human-approved generated
asset. No downloaded assets, Stytch artwork, provider, image generation, network
or paid calls are used. Intentional asymmetry is authored truth, so symmetry
cannot be used to manufacture a defect. Canonical references have the
`reference` role and cannot fill observation coverage. They are independently
projected from the frozen source, rather than derived from the conflicting
observation.

Run from the repository root with Python and an explicitly supplied native
binary; the binary is read and hashed, never copied into or modified by the
corpus:

```powershell
python scripts/qualify_geometry_diagnostics.py --native-library C:/path/to/bpt_core.dll --output tmp/geometry-qualification
python scripts/qualify_geometry_diagnostics.py --verify-only
python -m unittest discover -s tests -p test_geometry_diagnostic_corpus.py -v
```

`--verify-only` checks hashes without claiming that geometry ran. `--case ID`,
`--split calibration|heldout`, and `--quick` produce an explicitly incomplete
matrix. `--regenerate` deliberately recreates the versioned authored fixtures;
changed hashes require a reviewed corpus revision. Evaluation requires a real
native library: no fake backend or silent fallback is available.

The full plan evaluates raster/voxel pairs `(64,32)`, `(128,32)`, `(128,48)`.
This isolates raster sensitivity at fixed voxel size and voxel sensitivity at
fixed raster size. Canonical, reversed and rotated input orders run at the
baseline configuration. Operational cases run once with their own explicit
budget. Every analysis has a 15-second declared budget, except the intentional
0.001-second deadline control. Actual latency, budgets, native experiments,
sequential traces and abstentions are retained. Permutation acceptance compares
conclusions, localization and actions; sequential removal order remains
provenance, never a fault ranking. Resolution reports retain changed conclusions
and mean IoUs; both configurations must satisfy the same frozen expectations.
The report also retains normalized regional bounds at both resolutions,
unmatched regions, and actual missing/extraneous residual component bounds.
Matched labeled regions are checked against the sum of both measured
projection uncertainty bounds plus half a raster sample from each grid.
Nearest residual box distances are observations; semantic correspondence of
connected components across different grids remains unknown.

`qualification.json` records the manifest, original source/PNG hashes, actual
imported Python and worker source hashes, native binary hash, executable hash,
Python version, policies and policy hashes. Changed authorities invalidate the
run. Calibration and heldout assertion counts, misses, execution failures and
abstentions remain separate. Healthy passing controls prevent an engine that
returns no findings from passing. Regional controls prevent global mean IoU
from concealing a missing important part.

Each invocation creates a new directory under `runs/`; rerunning never erases a
previous failure. The top-level summary points to the latest actual run. Per
case/configuration/order artifacts include the common versioned diagnostic
report, observation record, original analytic source and **actual** full and
leave-one-out native reprojection overlays. Gray denotes intersection, red
input-only pixels, blue reconstruction-only pixels and white background. PNGs
depict actual masks, not decorative renders or an accepted correction.

Exit status is 0 only when selected assertions, report roundtrips, requested
permutations, sensitivity controls and source stability pass; 1 preserves a
measured failure and 2 reports missing/invalid dependencies. Only a passing
complete matrix can qualify this analytic D3 subset. Raw assertions and
abstentions remain visible rather than presenting synthetic accuracy as a
real-world precision estimate.

Silhouette consistency does not certify hidden surfaces, concavities, topology,
identity, appearance or final mesh delivery. D4–D8 remain explicitly unknown in
common reports, and D7 human/provider/end-to-end acceptance remains open. No
generative correction is executed or promoted by this command.
