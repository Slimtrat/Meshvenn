# Reproducible diagnostic evidence (D7 / #84)

The evidence command replays existing frozen D2–D6 corpora, verifies an original
3D reference, inspects an immutable real host-tool edit and produces a French
offline comparison/review page. It runs outside the pure engine. It never calls
a generation service, discovers credentials or assumes access to ImageGen quota.

```console
python scripts/qualify_diagnostic_evidence.py --native-library /path/to/bpt_core --require-complete-regressions --output tmp/diagnostic-evidence
```

`MESHVENN_TEST_NATIVE_LIBRARY` can provide the native library. Without it D3 is
`unknown/unavailable`; it is never counted as a passed matrix. `--corpus D4`
selects a partial replay explicitly. Existing per-stage policies, frozen labels,
case reports and overlays remain authoritative; aggregation does not fit a new
universal threshold. Each subprocess and its descendants have finite time
limits. The Linux/Windows evidence workflow builds the native library and
requires all five complete matrices.

Every run creates a new directory under `runs/`; earlier runs, failed calls and
corpus archives remain intact. `report.json` records per-case/split summaries,
source/manifest/policy fingerprints, raw evidence inventories, unresolved checks
and the descriptive real-image observations. Paths in exported inventories are
relative. Calibration and original heldout labels remain separate, with an
explicit `regression_exposed` flag: rerunning previously exposed cases is not a
new untouched statistical holdout. No baseline is replaced or weakened.

## Real trial: original robot badge

The mathematical Blender reference was frozen **before** the provider call.
`provider-v1/manifestfixture.json` is pinned at
`f0d1e6be24740cb4b38ce359613d8bf0f377f1bfae81b393f4e8d1c8ada0145f`.
Original geometry, cardinal orthographic cameras, a one-sided flag, PNGs, masks,
materials and provenance are GPL-3.0-or-later authored corpus data. No Stytch
production artwork, private photo or external licensed model is used.

The source GLB contains 31 meshes and 26,204 triangles, embedded geometry and no
external resources. The builder exports the exact file, empties the scene,
reloads the GLB and records component/world-position evidence before rendering
the reference views. The injected defect changes only the badge material from
blue to pink: 7,096 source pixels change, zero outside the independently authored
edit mask. The transparent 1,024-square input pair and edit selection were frozen
before the trial. The visible badge mask comes from geometric visibility; a
declared two-pixel dilation covers render antialiasing.

One built-in `image_gen.imagegen` host-tool edit was observed on 2026-11-16.
The exact prompt requests the blue badge while preserving the rest, image grid
and alpha. The tool returned in 57.354 measured seconds. Its original PNG is
**1,254 × 1,254**, despite the requested 1,024-square canvas; its badge is visibly
blue and its alpha edges contain additional artifacts. The unmodified result,
prompt, before/reference files, original GLB and caller-observed metadata are
sealed in `tests/fixtures/diagnostics/provider-attempt-v1`:

```text
packet SHA-256: 5c01bd5b596b017fe279d4da1b5ec89cc73a953919763f8efc9cc1acb7cafee8
output SHA-256: b2d87cff830961fcc079dd0d3b5b157b05dcbc896d897fa5a651aaf465432093
```

This is an observed failed preservation trial, **not a successful correction**.
The replay rejects the changed image grid. It neither resizes nor registers the
output to manufacture a better score, nor bypasses the existing PNG pixel
budget. A CRC-checked IHDR records the declared grid without claiming that an
oversized image passed the raster decoder. Same-grid comparisons record masked
RGB error, foreground alpha overlap and exact changes outside the mask; those
descriptive pixel measurements do not certify identity or geometry.
The explicit mask uses the existing D2 convention: alpha and maximum RGB must
both reach .5. An opaque black background is protected, not editable.

### Two directional differences

The report explicitly compares **before (1)** with **after (2)** on the original
fixed grid. Foreground sets contain coordinates whose alpha reaches .5:

- `1 − 2` identifies foreground that disappeared.
- `2 − 1` identifies foreground that appeared.
- Their union is the symmetric difference; it must be empty **outside the edit
  mask**. An equally sized deletion and addition cannot cancel each other.

This is set difference, not signed channel subtraction. Adding `(1 − 2)` and
`(2 − 1)` arithmetically would always yield zero and would prove nothing.
Exact decoded RGBA values are checked separately at every protected coordinate:
unchanged foreground can still hide a changed colour or alpha value. RGBA sets
contain `(x,y,R,G,B,A)`, so a changed pixel contributes an old sample to one
direction and a new sample to the other; neither is discarded by cancellation.

| Change outside the mask | 1 − 2 foreground | 2 − 1 foreground | Changed RGBA pixels | Preservation |
| --- | ---: | ---: | ---: | --- |
| None | 0 | 0 | 0 | Pass |
| One pixel removed and one added | 1 | 1 | 2 | Fail |
| Same foreground, one pixel recoloured | 0 | 0 | 1 | Fail |

The permitted badge recolouring need not have an empty **whole-image** RGBA
difference. Full-image counts remain in JSON; the preservation gate and HTML
table explicitly use the region outside the independently authored mask.
The healthy reference is used for colour-error measurements, not substituted
for the actual before image in these differences.

Two hashed diagnostic maps show unexpected removal/addition separately, with
the allowed edit region in green. They and the existing RGBA-change map are
available under the offline page's difference disclosure. Source images are
never modified to create these measurement maps. A wrong grid, unsupported
decoder or input budget produces unknown/null differences, never zero or an
empty-set claim. The archived 1,254-square provider output therefore remains
uncomparable and rejected; the original 1,024-square inputs are unchanged.

The backend model, usage and price were not exposed. They remain `null/unknown`,
including currency; unknown is never converted to zero. The trial was limited
to one observed host-tool call, with no service API invoice or paid retry.
Archival provenance is caller-observed, not a provider signature. Replay uses
cached bytes and incurs no new generation call. The skill's original output was
copied without retouching; every output and failure must be declared.

## Recheck, import and inspect

```console
python scripts/qualify_diagnostic_evidence.py --verify-only --output tmp/evidence-inspection
python scripts/qualify_diagnostic_evidence.py --attempt /local/closed/attempt.json --output tmp/evidence-import
python scripts/qualify_diagnostic_evidence.py --review /local/human-review.json --output tmp/evidence-with-review
```

`--verify-only` verifies bytes and compares archived pixels; it does not run the
diagnostic matrices. `--attempt` imports an already observed manifest, never its
tool. Its closed source directory must declare every file, including exact UTF-8
prompt bytes and raw execution provenance. Symlinks, traversal, special files,
stale hashes, hidden caches and mutable/reused archive destinations are rejected.
Assets live in content-addressed `objects/`; the packet preserves the exact
original manifest and a final seal. An interrupted unsealed directory is never
repaired silently. Every verification rereads bytes rather than trusting mtimes.
This profile binds the offered GLB and chosen input/mask bytes to this exact
reference fixture; a rehashed foreign GLB cannot inherit its reload proof.

`review.html` embeds the actual input/output PNGs, the original reference GLB
download and report. It works offline, uses no remote scripts/resources and
submits no responses automatically. It explains that this GLB is the source
reference; it was not reconstructed from the generated candidate. The form
requires a person's explicit attestation and experience selection. It saves
their observations as a separate JSON bound to exact packet/image/GLB hashes.
The import retains raw responses and unresolved/failed task answers. Missing,
pending, agent-authored or non-attested reviews never become a human pass.
User review files remain local by default; they are not committed automatically.

Command exit zero means the evidence command completed without a broken
regression/integrity check. It can correctly report a **failed or unknown quality
result** for the archived provider trial. For a delivery gate use:

```console
python scripts/qualify_diagnostic_evidence.py --require-qualified-delivery
```

That gate fails on a required unknown or failure. The current corpus cannot
qualify corrected delivery. This remains true even if all deterministic
regressions and a separate image review pass.

## Original GLB evidence and remaining acceptance

Archived GLB reload proof is distinguished from a fresh Blender process:

```console
blender --background --factory-startup --python-exit-code 1 --python scripts/build_diagnostic_reference.py -- --verify-glb-only --output tests/fixtures/diagnostics/provider-v1
```

The main CI executes this fresh read/reload check. `--output` with no
`--verify-glb-only` builds a new reference in a separate empty directory; it never
silently overwrites the frozen corpus. Raster bytes can differ across Blender
versions/platforms, so fresh observations do not replace the historic pin.
The byte-identical original authoring program is preserved in
`provider-authoring-v1`; the public builder is a guarded wrapper. Reference
verification explicitly maps the historic script fingerprint to that preserved
source and records current wrapper provenance separately. Neither the original
manifest nor the real provider packet is rewritten when the launcher is fixed.

#84 remains open for human-reviewed generated view-set coverage, general
semantic/provider quality and task-based **corrected** GLB delivery under #85.
The image review here is guided, not a blinded population study. A single edit
does not establish real-world rates, identity retention or hidden geometry.
The reference GLB does not substitute for an accepted corrected export. This
profile makes no animation, deformation or #60/#63 quality claim.
