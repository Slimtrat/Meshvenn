# Frozen analytic appearance corpus

`appearance-v1` is original mathematical fixture data for D4/#81. Its authoring
definitions, expected visible-region outcomes and required abstentions are
frozen **before any D4 diagnostic evaluation**. This first tranche does not
qualify a general semantic identity analyzer, generated views, physical hidden
surfaces or full #84 acceptance.

The corpus contains 22 cases at 32 and 64 pixels. The manifest has SHA-256
`5fc81e9563bd6ee03ebc5b6f8b2f2eb003b8283aaa04a1f481788f6b4533d5e3`.
`scripts.appearance_diagnostic_corpus.integrity.load_manifest` rejects changed
labels, original assets or authoring code. Generator source fingerprints use
explicit LF normalization so authored data can regenerate across operating
systems. These checks verify the data; they do not evaluate appearance quality.

## Original evidence and coordinate convention

The authoring scene consists of a closed box with a four-colour UV pattern,
three-dimensional triangle surfaces and a small striped motif. Additional cases
include a separate closed occluder or an intentionally coincident independent
surface. Vertices use the native `[-1,1]` cube. Triangle indices are authoritative;
UVs/material labels describe the independent authoring recipe, not a point cloud.

Fixture images are rendered with an independent brute-force Möller–Trumbore
ray/triangle loop. The generator imports no diagnostic BVH, visibility mapper,
UV reprojection, Blender renderer or engine under evaluation. Its camera equations
are stated in every authored source and calibrated by focused tests against the
shared native projection convention. Raster samples use bottom-left endpoint
coordinates `u=x/(width-1), v=y/(height-1)`; PNG rows are top-left. Shared triangle
edges use a stable source tie for authoring only; coincident independent surfaces
remain ambiguous expected truth.

Each input and reference has its original PNG hash, camera declaration,
photometry settings/proof, lineage and an independent visible-region truth mask.
PNG text tags distinguish original authored encodings without changing their
pixels. References are validated by exact mathematical authorship, **never by an
invented human review**. The model sources and original recipes are hashed.
No Stytch/Doll assets, downloaded imagery, model calls, paid services or external
artwork are included. The original mathematical data follows the repository's
existing GPL-3.0-or-later license.

## Frozen cases

| Cases | Expected knowledge |
| --- | --- |
| Healthy multicolour and healthy reprojection | Passing measured colour consistency on a supported common region; no global identity certification |
| Local colour and removed visible motif | Localized numerical failure overlapping the authored defect; an unaffected common region still passes |
| Intentional asymmetry | Authored asymmetry remains valid; no symmetry-based correction |
| Region hidden in reference or target | The hidden region is unknown, not a bad-colour attribution; visible shared evidence remains useful |
| Back region never observed | Its surface appearance is unknown; projected foreground cannot validate the hidden back |
| Unverified camera or coincident surface | Correspondence remains unknown |
| Declared neutral scalar gain | Explicit verified gain 0.65 is applied in linear RGB; calibrated comparison can pass while raw change stays recorded |
| Uncontrolled lighting | True albedo colour stays unknown even though the author knows the synthetic lighting gain |
| Reference derived from target or circular lineage | It cannot validate its own target |
| Accepted canonical design ancestor | The original accepted design can diagnose its descendant's local change |
| Stale declared source | Integrity failure and appearance abstention stay visible |
| Upstream geometry failure | The exact supplied upstream failure remains; D4 cannot promote the common report to pass |
| Semantic service unavailable/malformed/conflicting/low-evidence/supported mock | Adapter handling only; actual numeric checks still run, and mock responses never qualify semantic quality |

The scalar-gain and uncontrolled-lighting targets deliberately have identical
decoded pixels. Their epistemic difference comes from declared calibration and
hashed proof, not a fitted gain that silently becomes ground truth. Albedo uses
gain one; uncontrolled-lit inputs do not disclose the hidden authoring gain as
a calibration. Saturation or insufficient source support cannot establish colour.

The occlusion region has zero visible samples in its hidden view at both
resolutions. Its other view has four authored visible samples at 32 pixels and
27 at 64. The common healthy region has at least 16 visible samples even under
reprojection and is disjoint from the injected colour defect. Truth masks and
surface definitions remain separate from any diagnostic residual or heatmap.

## Review and acceptance boundary

The [PNG contact sheet](../tests/fixtures/diagnostics/appearance-v1/case-panel.png)
shows reference/target pairs and **author expectations**, not measured diagnostic
results. Mock cases explicitly say `MOCK ONLY`. The sheet itself is not diagnostic
input and its existence does not constitute human approval.

The planned evaluation uses both raster sizes and canonical, reversed and rotated
input orders. Calibration and heldout cases are separate; labels and thresholds
must not be changed after observing a failure. Reruns following an implementation
fix provide regression evidence on an exposed holdout, not new statistical
validation. Raw metrics, localization bounds, visibility abstentions, code/policy
and source fingerprints, budgets, timings and actual overlay evidence will be
retained by the qualification runner.

Healthy passing controls and required injected failures prevent an evaluator
that emits no findings from passing. A good global mean cannot substitute for
the named-region result. Numeric analytic outcomes and mock adapter outcomes
must be reported separately. Unexecuted stages and general semantic fidelity
remain unknown; initial D7 and #84 remain open.

## Offline qualification

Run from the repository with Python 3.11 or later; no renderer installation,
native library, model service or network access is required:

```console
python scripts/qualify_appearance_diagnostics.py --verify-only
python -m unittest discover -s tests -p test_appearance_diagnostic_corpus.py -v
python scripts/qualify_appearance_diagnostics.py --output tmp/appearance-qualification
```

`--quick` evaluates only the 32-pixel canonical-order subset and cannot establish
the complete matrix. `--case` and `--split` also produce explicitly partial
results. The complete run performs 132 actual analyses: 22 cases, two raster
sizes and three order labels. With two source views, reverse and rotate name
the same actual permutation; there are two distinct input orders, not three.
Every invocation receives the frozen 15-second deadline. The engine's sample
and work budgets, actual elapsed times and local mock calls remain recorded.

Every attempt receives a new directory under `runs/`; failures are retained.
`qualification.json` lists scope/partition metrics, every required assertion,
raw region counts and normalized bounds, order signatures, resolution changes,
Python executable/code/source/policy hashes and measured timings. The source
authorities are checked again after the run; changing engine or evaluator code
while measuring invalidates qualification. Heldout reruns after exposed failures
remain regression evidence, not an independent new holdout.

Each observation retains the exact strict D4 result, original engine report,
common report, original PNGs and authored sources. Actual status masks and
sampled source colours accompany separate raw and declared-correction delta
PNGs. White delta pixels are unmeasured, while black means measured zero; fitted
neutral gains are retained as diagnostics and never become calibration proof.
The common report explicitly keeps D5–D8 unknown. Supplied upstream failures
remain verbatim in `upstream_reports` with their hashes and an overall failure
gate; the upstream specimen tests composition, not native D3 quality.

Localization compares actual changed masks against independent author truth
masks after execution. Those truth masks are never passed to D4. Resolution
checks retain both the authored ROI and measured changed-mask bounds; their
explicit tolerance is one endpoint-grid pixel from each raster,
`1/(32-1) + 1/(64-1)`. A shifted measured localization cannot pass merely because
the authored ROI is unchanged. Full finding-signature differences are retained
even when both resolutions satisfy the frozen case expectations.

The workflow `appearance_diagnostic_corpus.yml` evaluates the real engine on
Ubuntu/Python 3.11 and 3.13 and Windows/Python 3.13, then uploads raw evidence even
on failure. Semantic service scenarios use local adapter mocks only; their
metadata explicitly lacks semantic qualification. Positive mock claims cannot
certify identity. The no-output control fails all 22 frozen cases, and a mock
that was never invoked cannot pass an adapter-only control.
