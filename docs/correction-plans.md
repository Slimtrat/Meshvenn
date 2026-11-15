# Offline correction plans (D5)

`core.correction_plans` converts immutable D2/D3/D4 reports into bounded proposals
and checked provider request packages. It performs no network request, generation,
image mutation or asset acceptance. The same pure implementation is packaged in
`meshvenn-engine` and exposed through the agent/MCP adapters.

```python
from core.correction_plans import (
    ProviderCapabilities, plan_corrections, prepare_correction,
)

capabilities = ProviderCapabilities(
    provider_id="my-adapter", version="1",
    controls=("region_edit", "mask", "multiple_references",
              "camera_request", "identity_reference"),
    max_references=8,
)
result = plan_corrections(view_set, reports, capabilities=capabilities)
for plan in result.plans:
    print(plan.action_kind, plan.readiness, plan.probable_cause.uncertainty)

# Selection is explicit; preparation recomputes the entire current authority.
edit = next(p for p in result.plans if p.readiness == "ready")
request = prepare_correction(edit, view_set, reports, capabilities=capabilities)
# A separate provider adapter may resolve the hashed image references and use
# request.prompt. Its output must be a new candidate followed by fresh checks.
```

## Routing

Source/mask/camera/alignment preparation takes precedence over generation for
both the target and its required references. Engine incidents and incomplete
reports require technical diagnosis or fresh evidence. Missing observations
request a useful camera; preflight 1.1 records missing azimuth/elevation as
structured measurements. Older reports without those measurements request
confirmation instead of extracting instructions from prose. For appearance
coverage, accepted reference cameras or a declared angular-gap heuristic can
suggest a view; usefulness and camera compliance still require verification.

Geometry residuals alone describe a suspect group. A same-camera accepted
canonical comparison can establish a conditional design mismatch, but it does
not establish physical truth. Multiple distinct same-camera authorities require
an explicit choice; a pairwise pass/fail ranking does not arbitrate them.

A local measured D4 color failure can produce a targeted edit when matching
visibility coverage is resolved and the original camera and accepted reference
lineage are supported. An identity assessment that remains unknown does not erase
this measured color evidence; identity stays an invariant and mandatory postcheck.
Unqualified model judgments do not acquire automatic edit authority. Conflicting
current reports for the same check/region require a reference decision.

## Original coordinates and annotations

D4 regions use original bottom-left normalized image coordinates. D3's flattened
report can mix aligned residual components with caller-authored important
regions, so the planner never guesses their coordinate frame. A geometric edit
requires an explicit `EditAnnotation` tied to the complete report SHA, finding,
original view/region and hashed provenance.

An annotation may carry a real inline `MaskArtifact` (binary, hashed, at most
256×256), describing a full-frame original-normalized edit-support grid. It must
preserve the original aspect ratio, never upsample its source, and contain no
occupied samples outside the named region. An adapter may need an explicit
resolution conversion for its provider; the package preserves the grid and frame.
A bounding rectangle is never turned into a fabricated mask or segmentation.

Explicit annotations constrain overlapping edits across duplicate findings and
reports. A sibling plan cannot omit an unsupported mask to obtain readiness.
Regions outside that annotated support remain separately reviewable. By default,
edits need four original pixels, two pixels on both axes, and at most 35% of the
image area; unresolved or overly broad targets request review instead.

## Capability negotiation

The provider-neutral controls are `region_edit`, `mask`, `multiple_references`,
`camera_request` and `identity_reference`. The default provider has no declared
controls. Every requested control is retained; unsupported controls or an
insufficient reference budget produce an `unsupported` plan with an explicit
alternative. References are not silently discarded.

Capabilities declare the ability to receive a request, not a promise that the
provider will obey it. `ready` means a request can be prepared against current
evidence; it is not generation success or quality acceptance. Other readiness
states are `needs_input`, `unsupported` and `blocked`. Preparation is only allowed
for supported `edit_region` plans. Local preparation and reference choices remain
inspectable tasks, never disguised provider edits.

## Invariants, postconditions and staleness

Packages snapshot the accepted references, target camera/alignment, original
source hashes, measured evidence, probable cause and uncertainty. They preserve
original user photographs, masks and intentional asymmetry. Target pixels outside
the local region and other views remain protected constraints. Generated outputs
are separate derived candidates; no original is overwritten.

Every plan requires fresh preflight, geometry, visible appearance, identity and
exact-export checks, with no new blocking failures or healthy-region regressions.
Baseline measurements and thresholds are retained. Neither a higher mean score
nor a completed provider request can override a lost component or unresolved
identity. D6/#83 implements subsequent execution and acceptance; D5 does not
pretend to have run those checks.

The context binds the view-set revision, complete report snapshots (including
findings and completion), capabilities, annotations, policy and implementation.
Report dependency fingerprints alone are insufficient because they omit measured
findings. Acquisition ordering of the same reports is normalized. Preparation
replans and requires an exact match, so copied context hashes, altered instructions,
removed invariants and stale cameras/masks/references/models/reports are rejected.

Defaults bound planning to 20 views/reports, 128 annotations, 4,096 findings/regions,
64 plans and 20 seconds of cooperative work. The deadline includes context
processing. Cancellation or exhaustion preserves an explicitly incomplete result;
unprocessed bindings authorize no plan. Exhausted plan lists are partial and
cannot be prepared. Every D5 `verification_status` remains `unknown`.

The frozen corpus qualifies plan routing, constraints, packaging and guards on
actual diagnostics and explicit contract controls. It does not qualify a real
provider, human identity judgments or the artistic quality of a generated edit.
See [the corpus protocol](correction-plan-corpus.md). Issues #81/#84 remain open
for their broader semantic and end-to-end qualification work.
