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
retained by the qualification runner once the D4 API is available.

Healthy passing controls and required injected failures prevent an evaluator
that emits no findings from passing. A good global mean cannot substitute for
the named-region result. Numeric analytic outcomes and mock adapter outcomes
must be reported separately. Unexecuted stages and general semantic fidelity
remain unknown; initial D7 and #84 remain open.
