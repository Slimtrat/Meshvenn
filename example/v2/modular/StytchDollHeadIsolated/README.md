# Head-isolated Stytch doll, V1 candidate

This is a **distinct skinning candidate**, not a silent replacement for the
accepted `../StytchDoll` / v0.1.182 bundle. It does **not** resolve issue #60:
shoulder/torso collapse and canonical neck/head pivots still need qualification.
Stytch consumer acceptance of this new fingerprint is not claimed.

## Retained and intentionally changed

- Same 7,128 native vertices, 7,126 quads / 14,252 exported triangles, exact
  source positions, UVs, materials and embedded two-view atlas.
- Same eighteen native rest joints and inverse binds; five face-authored regions,
  eight authored sockets, zero clips. Head/neck remain in `body-core`; open
  removed-limb seams are retained without caps.
- 2,150 vertices intentionally receive new head-transition weights. A persistent
  closed neck narrowing drives smooth mass transfer to the existing `head`
  joint. Below the observed transition, original weights remain exact.
- Original 56.02% neutral bake fallback and one UV overlap remain unqualified.
  No new views, repainting, consumer geometry repair or neural rigging are used.

`manifest.json` records both fingerprints, the native and decoded-accessor
envelopes, exact retained-source proof and ordinary No Rebuild export gates.
`reference.glb` is the accepted **old-weight** full-body baseline; it is not an
unchanged-weight fidelity oracle for this intentionally edited candidate.

## Product workflow

Canonical Biped V2 now observes a closed central neck narrowing during binding.
Missing/open/ambiguous evidence, disconnected props or raised lateral appendages
retain the regional solver's existing weights. V1 is unchanged.

For an existing V2 source, select the authoritative mesh (`MeshvennScan`, not a
`Doll_*` region preview) in Object mode and choose **Isolate Head Weights** in
the Canonical V2 settings. The operation is undoable, refuses repeated transfer,
precomputes all edits, and restores exact original weights on failure. Stale
derived previews are hidden; the edited original is shown. Export it through
**Export Authored Source (No Rebuild)**. The rig and atlas are not rebuilt.

Reproduce this bundle from the accepted fixture, in a separate empty directory:

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/refine_workshop_doll.py -- --output /tmp/head-isolated
blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_head_refinement_smoke.py -- \
  --variant /tmp/head-isolated --output /tmp/head-isolated-smoke
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/benchmark_head_isolation.py -- \
  --candidate /tmp/head-isolated --output /tmp/head-isolated-quality
```

## Actual GLB probes, not animation claims

`quality/quality.json` and six hash-linked PNGs come from reimporting the exact
GLBs. Seven explicit native-joint probes cover both arms, chest twist, head yaw,
head pitch, neck pitch and a compound pose. Worst cranial rigid residual falls
from 0.151183 to approximately 0.000000400 model heights. The fixed head cohort
is rest `Z/height >= 0.73`; neck strain is separately reported, never hidden.
These bounded tests prove head isolation, **not** artistic/neck/Hall/walk/mobile
qualification. In particular, the torso opening in the compound image remains.

The original source owner's bundle publication permission applies to this
derivative; no third-party CC0 claim is made.
