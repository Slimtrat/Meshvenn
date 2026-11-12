# Optional appearance semantic port

`core.appearance_diagnostics.semantics` defines a pure, versioned boundary for an
optional host-supplied vision/identity analyzer. It imports no provider SDK,
credentials, Blender, network client or filesystem resolver and initiates no
paid inference itself. A host explicitly supplies a `VisionAnalyzer` object.
The object and cancellation callback are runtime dependencies, never serialized
inside request data. No provider implementation or real semantic qualification
is included in this tranche.

```python
from core.appearance_diagnostics.semantics import (
    SemanticRequest, SemanticRegionPair, SemanticPolicy,
    make_semantic_image, analyze_semantics,
)

# The appearance engine has already verified the exact source buffers and has
# derived bounded original-source-space images and visibility/correspondence.
image = make_semantic_image(
    view_id=view_id, source=current_image_content_reference,
    original_decoded_sha256=decoded_buffer_hash,
    source_width=source_width, source_height=source_height,
    width=derived_width, height=derived_height, rgba=derived_rgba,
    color_space="sRGB", sampling="nearest-endpoint-grid",
    coordinate_space="source",
)
request = SemanticRequest(
    current_view_set, appearance_context_sha256,
    pairs=semantic_region_pairs, images=derived_images,
)
evaluation = analyze_semantics(request, analyzer=host_analyzer,
                              timeout_seconds=30, cancel=is_cancelled,
                              policy=SemanticPolicy(required=False))
# Add evaluation.engines when composing its D1 findings into a common report.
findings = evaluation.findings
```

## Actual image and source contract

`SemanticImageSnapshot` contains a stable view ID, the original D1
`ContentReference`, hash of the complete original decoded RGBA buffer, source and
snapshot dimensions, actual RGBA samples, color encoding, sampling declaration,
coordinate space and a derived content hash. Snapshots are full-frame source
images in bottom-left coordinates with straight alpha. Declared alignment and
camera Flip X have **not** been applied to their pixels. D4 correspondence and
visibility already account for those transforms; semantic ROI bounds use the
original source frame.

The host supplies the actual derived samples. `make_semantic_image` validates and
hashes them; it does not decode, resize, crop, align or rewrite source images.
Supported encodings are `sRGB` and `scene-linear`, with normalized channels.
Endpoint nearest-neighbor sampling is explicit. Snapshots preserve source aspect
ratio within pixel quantization and do not upsample. A derived hash covers
original/decoded provenance and declared sampling metadata plus big-endian
float64 RGBA, using the `bottom-left-straight-alpha-rgba-f64-be-v1` domain. It is
never claimed to be the original encoded PNG digest.

At most 20 snapshots of at most 128 pixels per axis are accepted, with original
sources bounded at 1,048,576 decoded pixels each. The semantic request has a
32 MiB default byte budget. It includes the current `ViewSetRevision`, appearance
context hash, actual image snapshots, named region pairs and requested kinds.
The context hash binds additional current D4 dependencies. Its deterministic
fingerprint covers the exact canonical reference, images/snapshot hashes,
regions, visibility evidence and source transforms. Source acquisition order is
provenance rather than an identity decision. The retained request contains actual
RGBA, so an adapter needs no implicit file resolver. An external adapter may
convert these pixels to its provider's format under its own declared policy.

## Region, lineage and evidence checks

Each `SemanticRegionPair` declares `pair_id`, exact target/reference D1 `Region`,
original target/reference image hashes, visibility states, hashed D4 evidence,
reference-lineage state and visible correspondence count. Default minimums are
16 visible correspondences, 16 region samples and two samples along each region
axis in the actual semantic snapshot. A smaller important part stays unknown;
a broad score does not qualify an unresolved named part. The helper checks the
current reference/image IDs and digests before invoking an analyzer.

Both regions must be visible, explicit, sufficiently sampled and present in the
current request. The reference must belong to the current validated canonical
design baseline with validation evidence. The host's lineage classification must
be `accepted`. `target_derived`, `circular` and `unknown` abstain. A canonical
ancestor of the target is intentionally permitted: D4 compares a candidate to an
accepted design, unlike independent-observation attribution in D3. Shared source
ancestry is not blindly treated as disqualification. The host supplies this
classification from its authoritative lineage analysis; this module does not
infer temporal ancestry by treating identical hashes or masks as view revisions.

An analyzer cannot replace those visibility or lineage declarations. Its claims
must echo the exact current pair ID, target/reference regions and requested kind;
new/shifted regions, foreign references and stale request fingerprints are rejected.
Hidden, unknown or underresolved regions never receive supported judgments, even
if a model returns confident text about them. If every region lacks usable
evidence, no inference call is made.

## Port and returned claims

The host implements:

```python
class MyAnalyzer:
    def metadata(self):
        # Static SemanticAnalyzerMetadata(analyzer=EngineVersion(...),
        #                                 model=EngineVersion(...)).
        return metadata

    def analyze(self, request, *, timeout_seconds, cancel=None):
        # Honor the remaining timeout/cancellation in the external adapter.
        # Return SemanticResponse or its exact finite JSON object.
        return response
```

`SemanticResponse` is schema version 1, binds `request_fingerprint`, identifies
the exact declared model/version and contains at most 512 claims. A claim includes
`claim_id`, `pair_id`, `kind` (`identity`, `accessory`, `motif`), verdict
(`consistent`, `changed`, `unknown`), exact target/reference regions,
explanation, explicit uncertainty, support (`sufficient`, `limited`, `none`) and
optional confidence. Unknown fields, unsupported versions, duplicate claim IDs,
nonfinite numbers and serialized objects/callables are rejected. The default
response limit is 512 KiB; explanations/uncertainties are individually bounded.

Absent/malformed services, missing claims, mismatched models, stale snapshots,
weak support and conflicting judgments produce explicit `unknown` results.
`SemanticAnalyzerUnavailable` reports host service absence; `TimeoutError` and
`InterruptedError` have explicit outcomes too. Contradictory claims for the same
pair/kind abstain without selecting the higher-confidence one. All bounded raw
adapter JSON is retained with SHA-256, including invalid-schema, stale, late or
cancelled responses. Non-JSON/oversized data may be rejected before a full raw
hash can be produced; that absence is explicit rather than a fabricated digest.
The digest covers canonical adapter JSON, not an unavailable provider HTTP body.

Confidence is always an uncalibrated model score. No confidence-calibration field
is accepted. The default 0.5 floor is an explicit abstention heuristic, not a
probability calibration or empirical quality guarantee; hosts can change or
disable that floor. Missing confidence is allowed when support is explicit.
Returned D1 interpretations use `Judgment(kind="model")`, record model version,
uncertainty and `confidence_calibrated=False`, separately from hashed source,
visibility and execution observations.

Adapter metadata can additionally declare `qualification_evidence` (a hashed D1
`ArtifactReference`) and `qualification_kinds` (a subset of identity/accessory/motif).
The record belongs to the trusted adapter/host and is bound to the exact model and
evaluation fingerprint; it is not accepted from the model response. Declaring a
qualified kind without evidence is invalid. The semantic layer records this host
assertion, not a scientific audit of the referenced qualification dataset.
Qualification evidence never calibrates model confidence automatically.

`evaluation.metadata`, `evaluation.qualification_evidence` and
`evaluation.qualification_kinds` expose that declaration to the parent appearance
engine. Optional PASS/FAIL findings remain model opinions. The global identity
assessment must remain unknown for an unqualified analyzer, including every mock
in the diagnostic corpus; a model's `consistent` response alone cannot promote
identity fidelity. Only the parent engine applies its policy to an explicit
host qualification record and the supported current claims.

## Outcomes, timing and qualification

`SemanticEvaluation` retains the immutable request and fingerprint, policy,
engine/model versions, per-region evaluated claims, composable D1 findings,
bounded error/time metadata and raw response JSON/hash. Its dependency fingerprint
also includes policy and engine versions. Findings are optional by default;
hosts may require the semantic checks under their declared appearance policy.
Every model version in a finding must also be included in the composed report's
engines. A returned model judgment is not a deterministic identity observation.

States distinguish `complete`, `unavailable`, `invalid_request`,
`malformed_response`, `model_mismatch`, `stale_response`, `insufficient_evidence`,
`timed_out`, `cancelled` and `service_error`. Complete means that the adapter
protocol completed; individual judgments can still be unknown. No state or
semantic finding can overrule a failed geometry check or an unknown export check.
Suggested actions only request review; no image deletion, generation, revision
promotion or source mutation is performed.

Preparation, metadata and inference share one elapsed deadline, bounded at 120
seconds. The port receives the actual remaining allowance and cancellation
callback. **The host port must honor them.** This module cannot hard-kill an
arbitrary Python callback, SDK call or thread. A response returning after its
deadline or cancellation is preserved and remains unknown. Hosts needing hard
isolation must provide it outside this port. Error messages do not copy arbitrary
provider exceptions or credentials.

Run adapter tests with:

```sh
python -m unittest tests.test_appearance_semantics
```

These tests use synthetic images and fake model responses solely to qualify the
strict adapter, provenance, abstention and D1 composition behavior. They do not
qualify real semantic identity fidelity. Real service/model evaluations, false
positive/negative rates and held-out image evidence remain an explicit later
corpus qualification; this does not close D7/#84 or appearance/export delivery.
