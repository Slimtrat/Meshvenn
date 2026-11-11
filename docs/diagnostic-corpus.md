# Offline diagnostic corpus and measured qualification

This is the initial D7 tranche for [#84](https://github.com/Slimtrat/Meshvenn/issues/84),
covering shared D1 contracts and real D2 preflight behavior. It does not close #84.
D3–D8, human-reviewed generated inputs, provider fidelity, generative corrections,
GLB delivery and acceptance by people without 3D expertise remain `unknown`.

The corpus contains 21 original analytic cases, each at 128 and 256 pixels.
Eleven are calibration controls; ten are held out for evaluation. Their case IDs,
defect parameters and expectations are versioned in
[`tests/fixtures/diagnostics/v1/manifest.json`](../tests/fixtures/diagnostics/v1/manifest.json).
The parameters were frozen before the full evaluation. The runner uses the
preflight's published policy defaults; it neither fits thresholds nor modifies
heldout labels in response to measured outputs.

When an implementation is corrected after observing a heldout failure, rerunning
these same frozen cases supplies regression evidence. It is not a fresh,
untouched statistical holdout or a calibrated estimate of real-world accuracy.

## Truth and provenance

The source is a mathematically authored union of axis-aligned boxes, projected
exactly at the four native cardinal orthographic cameras. The raster convention
is bottom-left, with `u=x/(width-1)` and `v=y/(height-1)`, inclusive rectangle
edges. Projection tests compare the analytic rectangles to the repository's
camera math. A small flag, depth-asymmetric backpack/nose and unequal arms make
the controls informative without assuming bilateral symmetry.

Each case records its boxes, source hash, original PNG hashes/dimensions, true
analytic camera, declared camera, injected defect, expected observations,
ambiguity and split. Camera verification and canonical validation cite the
hashed analytic source. Canonical `validated=true` means exact analytic
authorship in this corpus; it does not mean a human approved a generated image.
Reference views are independent projections of the frozen source and have the
`reference` role. They cannot fill missing observation coverage.

This is **synthetic truth**, not real-world ground truth. It provides exact
knowledge of injected changes and camera declarations. It does not establish
performance on photographs, generative views, textures, occlusions, topology,
identity or production 3D assets. No downloaded assets, Chamber props, Stytch
artwork, AI-generated images, credentials or paid calls are used. Mathematical
regression data follows the existing GPL-3.0-or-later repository license; no
production asset is relicensed.

## Cases and what is actually evaluated

| Cases | Measured D1/D2 expectation | Deferred knowledge |
| --- | --- | --- |
| Healthy and heldout healthy | Source integrity, camera support, coverage, alignment tolerance; no unexpected warnings/proposals | Silhouette agreement does not certify 3D fidelity |
| Bounded shift/scale and heldout variants | Localized `alignment.suspected`, measured improvement and recovered inverse transform within raster tolerance | Proposal remains unaccepted; no generative correction is executed |
| Crop, empty mask, empty alpha, alpha/mask mismatch, both empty | Specific input failure, reduced usable coverage and registration abstention | No attribution to a generative or geometry cause |
| Unsupported perspective and ambiguous/wrong declared camera | Unsupported/unverified camera, incomplete usable coverage, registration abstention | The runner knows the synthetic true camera but does not give that hidden answer to preflight |
| Duplicate and missing views; single view | Duplicate ambiguity or insufficient coverage, including view localization | Duplicate pixels can also describe symmetry; no automatic blame |
| True local proportion mismatch | `alignment.shape_mismatch=unknown`; no uniform transform proposed to conceal the change | D3 geometry localization/attribution is unknown |
| Missing small part | A real, hashed silhouette difference; no spurious global alignment proposal | D2 global IoU may pass alignment tolerance. Small-part detection is **not** qualified; D3 remains unknown |
| Intentional asymmetry | Known asymmetry remains canonical; healthy checks pass without correction | No general semantic asymmetry recognition claim |
| Engine failure contract | Failed completion with `engine.native_execution=unknown` roundtrips without claiming success | This is a declared contract specimen. No D3 native engine or actual native failure was executed |

Required failures and abstentions include expected verification states and
affected views. The manifest also names required **passing** controls for each
healthy/unaffected input and camera. An engine emitting no findings cannot pass
these controls. Unexpected failures **and** unexpected abstentions count as false
positives. A wrong view or wrong verification state cannot satisfy an expected
observation. Admissible secondary signals are declared before evaluation and
earn no true positives. Status counts and all abstained codes remain visible.

## Run without Blender or external services

From the repository root, using Python 3.13 and only the standard library:

```powershell
python scripts/qualify_diagnostics.py --output tmp/diagnostic-qualification
python -m unittest discover -s tests -p "test_diagnostic_corpus.py" -v
```

The command validates source and asset hashes first, then invokes the real
`core.diagnostics_preflight.analyze_preflight` on original decoded PNGs. It
evaluates both splits, both resolutions and three view orders: canonical,
reversed and rotated. The order checks compare actual conclusions, dependencies
and proposals, not fixture metadata. Resolution checks compare conclusions and
normalized alignment parameters. The tolerance is three pixels on the coarser
grid; actual before/after IoUs and inverse-transform errors are reported.

Useful narrower commands:

```powershell
python scripts/qualify_diagnostics.py --case bounded_shift --output tmp/diagnostic-shift
python scripts/qualify_diagnostics.py --split heldout --output tmp/diagnostic-heldout
python scripts/qualify_diagnostics.py --verify-only
```

`--verify-only` checks corpus integrity and explicitly does not qualify any
diagnostic. A case/split subset reports only its own measured assertions; it
does not publish the full matrix's qualified-capability list. An explicit
`--regenerate` recreates the versioned fixtures from their frozen definitions.
Review any changed hashes or expectations as a corpus revision, not a way to
make a failing evaluator pass.

## Outputs and acceptance boundary

`qualification.json` has schema version 1, corpus/manifest/policy hashes,
per-split precision/recall, false positives, misses, passing and missing controls,
abstentions, execution failures, per-case observations, order checks and
resolution sensitivity. It hashes the actual imported D1/D2, projection and
corpus source files under public module names, records the Python version and
uses these inputs in the qualification identity. The implementation fingerprint
also participates in common-report dependencies. A source change during a run
invalidates qualification. No machine paths or user names enter this provenance.

Total, per-case, canonical preflight and permutation latency are measured with
`time.perf_counter`; they are observations of the local run, not a product SLA.
Provider calls and paid API cost are explicitly zero. Undefined ratios are
`null`, never a fabricated 100%.
Each case/resolution directory contains a common versioned
`diagnostic-report.json`, its hashed analytic source, its observations and real
pixel-difference overlays.

Overlay colors are gray for intersection, red for reference-only, blue for
observed-only and white for background. `before` uses the actual decoded mask;
`proposed` applies the actual preflight proposal through `ProjectionAlignment`.
An overlay is evidence of those masks and mapping, not a geometry reconstruction
or an accepted correction. Artifact hashes are included and linked from the
common findings. All future checks have explicit `unknown` findings and reasons.
Reports retain partial completion (failed for the engine contract specimen), so
a healthy preflight cannot silently become full product acceptance.

The committed [measured development record](diagnostic-corpus-baseline.json)
preserves the initial failure and corrected run on the **same manifest**:

| Observation, 42 case/resolution variants | Initial implementation | Corrected implementation |
| --- | ---: | ---: |
| Required signal matches | 64 | 66 |
| Unexpected findings / missed signals | 2 / 2 | 0 / 0 |
| Passing controls / missing controls | 786 / 0 | 786 / 0 |
| D2 abstained-code counts | 28 | 26 |
| Execution failures | 0 | 0 |

The corrected run passes all 84 order comparisons and 21 resolution comparisons,
with eight proposals within the declared analytic parameter tolerances. Local
elapsed time was 114.63 seconds. Its complete source hashes, Python version,
policy hashes and per-case latency are recorded. The initial development run
predated source-hash instrumentation and explicitly retains that limitation.

Representative common reports and their actual overlays are versioned for the
[initial heldout-scale failure](diagnostic-corpus-evidence/initial-scale-heldout-256/diagnostic-report.json),
[corrected heldout scale](diagnostic-corpus-evidence/scale-heldout-256/diagnostic-report.json)
and [missing small part](diagnostic-corpus-evidence/missing-small-part-256/diagnostic-report.json).
The last example deliberately keeps part-fidelity `unknown` even though its D2
global alignment is within tolerance. These results qualify the stated analytic
subset; they do not qualify later stages or real-world/provider accuracy.

The command exits 0 only when selected measured expectations, roundtrips,
proposals and requested sensitivity checks pass. It exits 1 on measured failures
and 2 when the corpus/dependencies cannot be evaluated. `complete_matrix=true`
requires every case, both resolutions and all three orders. Success qualifies
only the stated analytic D1/D2 subset. The dedicated CI workflow preserves the
actual reports, scores and overlays as artifacts even when qualification fails.

## Extending the corpus

Add versioned, licensed reference assets and genuinely human-reviewed generated
views as later stages become executable. Preserve original evidence separately
from candidates; declare truth that is known, ambiguous or unavailable. Add
small-part/region metrics, real reconstruction failures, leave-one-out geometry,
appearance/visibility, correction identity preservation, accepted/rejected
before/after examples, end-to-end completion, cost and latency at their own
qualification gates. Provider mocks may validate orchestration, never qualify a
provider's visual fidelity. Full #84 remains open until those acceptance records
exist.
