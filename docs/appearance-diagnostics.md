# Appearance evidence (D4)

`core.appearance_diagnostics` compares original images through a declared
normalized triangle surface. It is read-only, works without Blender or a vision
provider, and uses the same camera projection and alignment as reconstruction.
No image, texture, mesh, accepted reference or scene is repaired automatically.

```python
from core.appearance_diagnostics import (
    AppearancePolicy, AppearanceViewSettings, analyze_appearance,
)

result = analyze_appearance(
    view_set, inputs,
    surface=surface,                    # SurfaceMesh, coordinates [-1, +1]
    view_settings=photometry_by_view,    # producer evidence, not inferred gain
    regions=original_image_regions,
    region_anchors=authored_surface_regions,
    upstream_reports=(geometry_report,),
    policy=AppearancePolicy(),
    vision_analyzer=None,               # optional trusted host port
)
print(result.report.verification_status, result.identity_status)
restored = type(result).from_json(result.to_json())
```

The standalone library exposes the same implementation under
`meshvenn_engine.core.appearance_diagnostics`. The engine facade action is
`appearance.diagnose`; the agent/MCP adapter delegates to that boundary.

## What is measured

Original bottom-left image grids cast rays against a bounded pure-Python BVH.
The native projector's null-space direction handles elevation, FlipX and
registration. Observations project to accepted canonical views, and canonical
views project back to observations. This reverse pass retains expected features
that are hidden in the candidate. Opposite sides are never mirrored. Intentional
asymmetry is therefore not itself a defect.

Each pair stores original UV coordinates, triangle IDs, visibility reasons,
scene-linear raw and corrected RGB, residuals, and separate expected, visible,
comparable, changed and unknown masks. Occlusion, grazing, ambiguous intersections,
unsupported cameras, insufficient alpha and unresolved texture boundaries abstain.
A hit on a triangle is lower-bound coverage evidence, not proof that its whole
area has been observed.

Named `Region` bounds always refer to the original image. A region without bounds
is unknown. An optional `AppearanceRegionAnchor` binds the expected feature to
authored 3D bounds and triangle IDs, with hashed provenance. Without that support,
a 2D rectangle can describe visible paint but cannot establish that the intended
part, rather than an occluder, occupies it. Anchored regions require the expected
surface to be visible; foreground occupying the rectangle cannot substitute.

The default color distance is maximum absolute scene-linear channel difference
with tolerance 0.06. Regions need eight samples and two pixels along both axes.
Localized connected changes need four pixels and two-pixel extent; smaller
changes remain unresolved. Local defects participate independently of the full
image mean. All thresholds are versioned policy inputs, frozen before corpus
evaluation rather than fitted to its expected answers.

## Lighting and references

Only verified producer declarations of albedo or calibrated neutral exposure,
including a hashed evidence record and known sRGB/scene-linear encoding, permit
color decisions. Declared calibration is an assumption, not an independent
measurement. Lit or unverified inputs preserve raw residuals but cannot assign a
paint defect. A fitted neutral gain is diagnostic evidence only; it never silently
calibrates an image. Clipping cannot be reversed.

Canonical views must belong to a validated, evidenced design reference. A
candidate derived from that accepted design is legitimate. A reference derived
from its target, a circular lineage, or conflicting accepted colors cannot judge
the target. Missing or conflicting evidence remains unknown.

## Identity and quality composition

The optional `VisionAnalyzer` port receives bounded, hashed original-space image
snapshots and supported region pairs. Adapter/model versions, full raw JSON,
confidence, uncertainty and supporting evidence are retained. Confidence is not
a calibrated probability. Malformed, unavailable, late, contradictory or poorly
supported responses abstain; timeout is cooperative at this in-process port.
Provider adapters requiring a hard deadline should isolate their work.

`appearance.identity_assessment` remains unknown without explicit host-declared
qualification evidence for that exact model/version and kind. A simulated
analyzer only validates orchestration. Neither the synthetic corpus nor mock
responses qualify real semantic quality; human-reviewed identity pairs and a real
provider evaluation are still required by issues #81/#84.

The default policy requires identity, so successful deterministic color checks
alone do not produce an overall pass. `require_identity=False` explicitly narrows
the report to sampled appearance; `identity_status` still remains unknown.
`deterministic_status` excludes semantic judgments, not upstream quality gates.
Full upstream reports are retained in `upstream_reports`; required
`quality.upstream_status` findings preserve their current pass/fail/unknown state.
A successful model judgment never overrides failed geometry or export.

## Replay and bounds

Source bytes and decoded-pixel hashes are distinct. The context binds view
revisions, accepted reference, mesh/provenance, authored regions, photometry,
policy, upstream report hashes and implementation source. Semantic dependencies
add model, adapter, qualification and semantic policy. Acquisition order alone is
not a new view revision. `is_stale` can compare explicit current source, policy,
engine, context and semantic dependency fingerprints without rewriting evidence.

Inputs are bounded to 20 views, eight observations/eight references and 4,194,304
total decoded image/mask pixels. Default grids are at most 64 pixels per axis;
65,536 total grid/pair samples, 8,000,000 BVH work units and a 30-second cooperative
deadline bound analysis. Budgets include additional counterpart rasters. A
cancelled or exhausted run retains completed evidence and yields partial/unknown,
never a completion-based success score. The caller's buffers are immutable.
