# Diagnostic contracts, version 1

`core.diagnostic_contracts` is the shared JSON boundary for Blender, command-line
tools and future service adapters. It imports no `bpy`, provider SDK or network
client. These contracts record diagnostics; they do not implement reconstruction,
camera estimation, model analysis, correction or downstream asset acceptance.

## Source snapshot

`ViewSetRevision(view_set_id, revision, views, canonical_reference=None,
input_order=(), schema_version=1)` records an exact source revision. Each
`ViewRevision` contains a stable `view_id`, positive integer revision, separate
`image` and `mask` content references, declared camera, `ProjectionAlignment`,
role and origin. Content references contain lowercase SHA-256 of original file
bytes, decoded width/height and media type. An unavailable image or mask is `None`,
so its absence can be diagnosed without inventing a digest or dimensions.
Distinct image/mask dimensions remain representable for input diagnostics.

Origins are `user`, `rendered`, `generated` and `derived`. Derived views require
`derived_from` hashes of original content; an altered documentary image is not
silently reclassified as an original observation. Roles are `observation`,
`reference` and `control`. `origin_details` can identify the producing operation.

`CameraDeclaration` records projection (`orthographic`, `perspective` or `unknown`),
optional angles, Flip X and verification state. `verified=True` requires supported
orthographic angles and hashed verification evidence. This flag declares a
producer's evidence; contract validation cannot certify its truth. Camera angles
and `.transform` reuse `ProjectionTransform` and `compile_projection`;
`.native_frame()` calls the existing `native_projection_frame` authority. Unknown
angles are `None`. A perspective declaration never becomes calibrated merely by
serialization or by producing geometry.

`CanonicalReference` has its own stable ID, revision, content hash, validation
state, optional proof and reference view IDs. A provisional render cannot replace
it without changing the dependency snapshot. Validation may describe an analytic
fixture or a human-reviewed reference; the producer documents that distinction.

## Report and evidence

`DiagnosticReport(report_id, view_set, engines, policy, resolution, findings,
assumptions=(), completion="complete", schema_version=1)` embeds the snapshot,
engine/model versions, policy ID/version/configuration hash and required check
codes, resolution with unit, explicit assumptions and completion state.
Completion is `complete`, `partial`, `failed` or `cancelled`.

`Finding` has a stable ID and lowercase dotted code, category, severity, verification
status, message, affected views/regions, evidence, interpretations, proposed actions,
required flag and reason. Codes are extensible; existing reports retain their code
meaning. Examples are `input.empty_mask`, `camera.unsupported`,
`alignment.suspected`, `geometry.cross_view_conflict`, `appearance.identity_drift`,
`coverage.insufficient` and `quality.export_failed`.

- Categories: `input`, `camera`, `alignment`, `geometry`, `appearance`, `coverage`,
  `engine`, `quality`.
- Severities: `info`, `warning`, `error`, `blocking`.
- Verification: `pass`, `fail`, `unknown`, `not_applicable`.
- Evidence kinds: `observation`, `artifact`, `execution`.
- Action kinds: `inspect_input`, `repair_mask`, `provide_view`, `verify_camera`,
  `select_reference`, `apply_alignment`, `review_reference`, `regenerate_region`,
  `diagnose_engine`.

Pass/fail findings require evidence. An observation requires finite measurements
or a hashed artifact; artifact evidence requires its hash and media type.
Execution evidence may record a technical outcome without pretending it measures
geometry. Measurement and threshold units must agree; threshold operators are
`<`, `<=`, `==`, `>=`, `>`. Units are explicit nonempty strings, for example
`pixel`, `ratio`, `degree` or `world_unit`. Regions optionally contain
`(left, bottom, right, top)` bounds in normalized bottom-left image coordinates,
inside `[0,1]` with positive area. All finding, evidence and action targets must
belong to the report's exact view set.

`Judgment` keeps an `inference` or `model` statement and its uncertainty separate
from observations. Model judgments require a model version also listed in report
engines. Confidence must be finite in `[0,1]` and is uncalibrated by default;
claiming calibration additionally requires hashed validation evidence. Contract
validation records that evidence; it does not validate calibration scientifically.

Unknown and not-applicable findings require an explicit reason. Missing required
checks, required unknown regions, empty checks, absent engine versions and
unfinished computations cannot produce `report.verification_status == "pass"`.
A required or blocking failure yields `fail`, even if other checks pass. Every
finding for a policy-required code participates, so a passing region cannot hide
an unknown or failing region. Explicitly justified exemptions can produce
`not_applicable`; that is distinct from a pass. Optional findings participate when
their code is policy-required or their severity is `blocking`.

The result certifies only the checks declared by that policy. A preparation-only
report does not certify geometry, appearance, animation or GLB delivery.

## Serialization and invalidation

All public contract dataclasses are frozen and normalize incoming lists to tuples.
They expose `to_dict()`, `to_json()`, `from_dict()` and `from_json()`. Root view-set
and report JSON must explicitly contain `schema_version: 1`. Readers reject unknown
fields, unsupported versions, duplicate JSON keys, malformed scalar types,
nonfinite numbers (including overflowing JSON exponents), dangling view targets
and invalid cross-field relationships. Booleans are not accepted as numbers.

Serialization emits UTF-8-compatible JSON text with sorted keys, compact separators,
finite normalized numbers and stable ID ordering for views, engines and findings.
No filesystem, image decoding, network request or external engine is invoked while
reading JSON. Declared content hashes must be verified against actual bytes by the
producer/consumer that opens those artifacts.

`report.dependency_fingerprint` is SHA-256 of the canonical dependency snapshot.
It covers images, masks, dimensions, view IDs/revisions/origins, camera parameters
and verification proof hashes, alignment, canonical reference content/revision,
engine versions, policy/version/configuration/required checks, resolution and
assumptions. Every finding is conservatively bound to this whole snapshot.
`report.is_stale(current_view_set, policy=..., engines=..., resolution=...,
assumptions=...)` compares it; `require_current(...)` raises for stale results.
Omitted keyword dependencies mean the stored value, so consumers must supply any
current engine/policy/configuration changes they intend to validate.

`views` are sorted by stable ID. `input_order` retains the acquisition/scan order as
provenance and is serialized, but is excluded from dependency fingerprints.
Artifact `uri` locations are also provenance; relocating identical hashed proof
does not invalidate a report. Permuting inputs cannot create a new blame ranking
through the contract. Engine permutation tolerance remains an algorithm test.

## Existing pipeline boundary

```python
from core.diagnostic_contracts import DiagnosticReport
from core.pipeline_contracts import PipelineStage, StageExecutionResult

diagnostic = DiagnosticReport.from_json(saved_report_json)
diagnostic.require_current(current_view_set, policy=current_policy)
result = StageExecutionResult.succeeded(
    stage=PipelineStage.GEOMETRY,
    implementation_id="native-hull",
    payload=existing_geometry_output,
    diagnostic_report=diagnostic,
)
saved_report_json = result.diagnostic_report_json()
```

Existing results can use immutable `with_diagnostic_report(report)` or
`with_diagnostic_report_json(text)`. Failed and skipped result factories also accept
diagnostics, so unavailable analyzers and engine failures preserve an explicit
report. `PipelineExecutionReport.diagnostic_report_for(stage)` reads that same
typed report after a run. Stage/pipeline technical `success` remains separate from
diagnostic verification and asset acceptance. No diagnostic stage, Blender object
or alternate pipeline is introduced.

Focused validation: `python -m unittest tests.test_diagnostic_contracts
tests.test_diagnostic_pipeline_boundary`. Tests cover typed JSON roundtrip,
rejection paths, missing evidence, unavailable model, ambiguous conflict,
engine failure/completion, required checks, blocking defects and stale sources.
