# Orthographic input preparation (D2 / #79)

`core.diagnostics_preflight` is a deterministic, read-only engine without Blender,
credentials, network calls or new dependencies. It consumes the shared versioned
`core.diagnostic_contracts` snapshots and produces their `DiagnosticReport`.
This prepares inputs; cross-view geometry/semantic diagnosis remains D3/D4.

## Integration

```python
from core.diagnostics_preflight import (
    RasterInput, ViewInput, AlignmentAnchor, PreflightPolicy,
    analyze_preflight, accept_alignment,
)

inputs = {
    "front": ViewInput(RasterInput.from_path("front.png"),
                       RasterInput.from_path("front-mask.png")),
    "ref-front": ViewInput(RasterInput.from_path("ref-front.png"),
                           RasterInput.from_path("ref-front-mask.png")),
}
# Construct ViewRevision image/mask references from original bytes/dimensions.
# For successfully decoded sources, raster.content_reference() supplies them.
# For unreadable sources, keep the unknown ContentReference as None: errors are
# still reported as failures rather than losing them as missing metadata.
anchors = (AlignmentAnchor("front", "ref-front", reference_evidence_sha256),)
policy = PreflightPolicy()  # required observation directions: 0/90/180/270
result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
report_json = result.report.to_json()

# After displaying original/reference/proposed masks and reviewing the proposal:
accepted = accept_alignment(result.proposals[0], result, view_set, inputs,
                            anchors=anchors, policy=policy)
geometry_mask = accepted.aligned_mask
appearance_source = accepted.source.image
appearance_mapping = accepted.alignment.source_uv
assert accepted.color_transform_sha256 == accepted.mask_transform_sha256
```

Persist the report with original source content and the proposal. Acceptance
reproduces the analysis and rejects changes to source bytes, decoded pixels,
revision metadata, reference evidence, cameras, policy or transform. The accepted
object retains immutable originals and exposes one mapping/certificate for both
consumers. `color_at(u,v)` provides nearest-neighbor RGBA on the identical pixel
grid as `aligned_mask`; existing appearance code may sample the original color
buffer through `alignment.source_uv`. Existing optional camera Flip X happens
after registration, following `ProjectionAlignment`'s convention. Do not pass an
already aligned color image through this mapping again. Promotion to a new
ViewRevision must be explicit and retain the original source hashes; this engine
does not silently rewrite files or source revisions.

An anchor requires a separate `role="reference"` view, inclusion in the canonical
reference's `view_ids`, `validated=True`, hashed canonical `validation_evidence`,
an explicit anchor evidence hash and an identical verified orthographic camera
(including Flip X). Reference/control views never supply required observation
coverage. Provisional reconstruction output must not be marked as independent
canonical evidence by its host. Generated camera labels without independently
archived verification remain unknown; this engine does not estimate cameras.

## Checks and findings

Stable codes include `input.unreadable`, `input.unsupported_format`,
`input.hash_mismatch`, `input.dimension_mismatch`, `input.nonfinite`,
`input.value_range`, `input.empty_mask`, `input.empty_alpha`,
`input.alpha_mask_mismatch`, `input.subject_truncated`, `input.duplicate`,
`input.segmentation_missing`, `camera.unsupported`, `camera.unverified`,
`coverage.insufficient`, `alignment.reference_missing`, `alignment.shape_mismatch`,
`alignment.suspected` and `alignment.within_tolerance`. Positive integrity,
occupancy, framing and camera-support observations are recorded too. Findings
carry measurements/thresholds or hashed source evidence and actionable next steps.

Boundary contact fails the framing criterion and records a **risk** of truncation;
it does not prove a missing anatomical part. Color alpha is compared to the mask
only when alpha actually segments the image. Fully opaque color is valid with an
explicit mask; without one, segmentation is unknown. Mask occupancy uses alpha
at least 0.1 and maximum RGB at least 0.5. Hosts must provide a subject mask, not a
photo mislabelled as a mask. Identical original color bytes at different cameras
produce an optional unknown review finding; identical silhouettes alone do not
condemn legitimate symmetry. Missing references and unresolved shape differences
remain unknown rather than requesting generative correction.

Default registration bounds are uniform scale 0.8–1.25 and offsets ±0.15 image
width/height. Healthy IoU ≥0.98 preserves the exact original, including intentional
asymmetry. A proposal requires native-grid after-IoU ≥0.97 and improvement ≥0.05.
The bounded fit rejects unequal axis scale and off-canvas subject loss; it never
rotates, mirrors or warps a silhouette. These are explicit preparation-policy
thresholds, not calibrated probabilities or guarantees about small semantic parts.

## Decoder and computation limits

The supplied file adapter accepts strict CRC-checked, 8-bit, noninterlaced PNG in
grayscale, grayscale+alpha, RGB or RGBA, including all five PNG row filters.
Palette, color-key transparency, interlaced/16-bit PNG and other formats produce
an explicit unsupported-format unknown; a host may supply a qualified decoder.
Corruption, empty files, invalid compressed lengths and over-budget input fail.
Encoded input is capped at 32 MiB and decoded input at **1,048,576 pixels per
raster** before PNG pixel allocation. The engine never silently resizes an input
or changes its declared original hash/dimensions to satisfy this limit.

`RasterInput.from_pixels` accepts normalized, straight-alpha float RGBA in
bottom-left order from a trusted host decoder. With original `source_bytes`, its
content reference hashes those bytes; the host is responsible for truthful
decoding. Without them, the explicit buffer media type hashes a canonical buffer
(big-endian signed int64 dimensions, then float64 RGBA). Each report additionally
binds actual decoded-buffer hashes, so changing pixels while retaining an encoded
hash invalidates an accepted proposal.

Similarity search evaluates at most 125 candidates on at most 128×128 pixels,
then validates the winner against the full native source grid and normalized
reference grid. Before/after evidence always uses those complete masks. Reduced
search can conservatively abstain on fine detail; it cannot accept a winner that
fails full-grid thresholds. Input validation and final validation are linear in
native pixel count. Sorted view IDs and dependency fingerprints make analysis
independent of input ordering; raster quantization can change measured IoU across
resolutions, and this is not an assertion of geometric invariance.

Run focused tests after integrating D1 with
`python -m unittest discover -s tests -p test_diagnostics_preflight.py`.
