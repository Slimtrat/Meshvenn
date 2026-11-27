# Cloth dummy: source LOD and exact consumer replay

This authoring path is outside engine policy. It uses the existing Geometry,
Rig, modular ownership, source preparation and ordinary GLB exporter APIs. It
does not add a rig fitter, partitioner or rendering workaround to Stytch.

The full-body `stytch-dummy-cloth-v1` reference remains immutable at
`c5d79f03057fe84264a1fa9231bc31e71f42c971324ae0a08009c339b760b65d`.
The new [modular candidate](../example/v2/modular/StytchDummyCloth/) preserves its
three embedded fabric maps, eighteen native joints and disabled normalization
(`false`, `null`, `1`). It has five explicit regions, eight joint-local sockets,
17,512 triangles, open shared seams and no caps, animation or collision proxies.

## What is qualified

- Rest source/LOD approximation: bidirectional vertices and triangle centers to
  triangle surfaces; max 5 mm, p99 2 mm, no increased observed boundary or
  nonmanifold edge count, max discarded skin mass 3%, unchanged native rest rig
  and material pixels. These finite samples are not a continuous Hausdorff proof.
- Source/LOD pose approximation: the same budgets on eight exact original
  Stytch presence/held captures, sixteen distinct native joint probes and rest.
  The source rest frames are verified before applying any capture. The old
  captures are reference/LOD comparisons, not new consumer captures or Walk.
- Export and reopening: ordinary mandatory roundtrip plus public No Rebuild.
  Public CI imports both GLBs, tests sixteen native probes and rest, compares
  all embedded image bytes and PBR fields, and renders four matched views.
- Render samples: at least 0.98 silhouette IoU and at most 0.04 interior linear
  RGB RMSE. The measured four-view IoU exceeds 0.998. Normals use the direct
  blended skin basis, not Blender's recomputed posed geometric normals.

These checks certify bounded fidelity to the supplied source. The source's
arm creases are still visible. They do not certify anatomical quality, actual
Stytch Walk/Hop/leg/equipment/missing-module/contact behavior, human acceptance
or distribution rights. The candidate is not selected or admitted. Issue #103
remains open; collision proxies and physics qualification remain #100.

The separate [Stytch numeric receipt](../example/v2/modular/StytchDummyCloth/evidence/stytch-native-receipt.json)
now records six passing native candidate campaigns for the exact `2df4fcf7…`
artifact, including the full factory, Hop/Walk/Held clearance, missing regions,
equipment, native-body variants, foot grounding and replay identity rejections.
The producer independently read those six local exact-asset receipts. This is
not a MeshVenn CI replay or downstream gameplay/packaging/mobile/rights
admission. Private app captures/code/buffers remain external. The older `d49…`
failure is not repointed to the passing identity; the asset family ID is
disambiguated by variant and SHA.

## Why the initial LOD was rejected

Rest-only decimation hid large posed errors. The first protected candidate
`d49ffad5…` passed rest/structure but failed source pose fidelity by almost
30 mm and failed its elbow/shoulder profile. Stytch also rejected its native
Hop arm clearance. It remains an immutable failed local candidate.

Barycentric transfer alone did not suffice: reduction also has to retain the
geometry where skin weights vary. The final recipe protects strong weight
gradients and fifth-influence risks, transfers the original triangle skin
field, and protects vertices identified by the failed pose report. Forty-eight
feedback vertices were sufficient in this run. Tiny influences are explicitly
removed in source authoring before qualification, because the Blender GLB writer
would otherwise omit them after the source checks. Their loss is included in
the same 3% budget. No export, consumer or profile tolerance was relaxed.

Rejected candidates, fixed budgets and failed measurements are retained in
the evidence ledger; no failing candidate becomes a selected skin. Native
source topology already had 24 observed nonmanifold edges; this does not claim
a new watertight certificate.

## Reproduce

Use Blender 5.2.1 with `--background --factory-startup --disable-autoexec
--python-exit-code 1`. Keep the pinned original native source outside all output
directories; its SHA is
`5f4c2730c8a5be475d68462e38d1d054fe8fedb0d4f0d476707421276febe1f5`.
It is an exact local authoring input, not an inference from the GLB's bounds.

```text
blender [flags] --python scripts/audit_cloth_replay.py --
  --source ORIGINAL.blend --asset ORIGINAL.glb --capture CAPTURE_DIR --output NEW_AUDIT
blender [flags] --python scripts/cloth_lod.py --
  --source ORIGINAL.blend --feedback FAILED_FIDELITY.json --output NEW_LOD
blender [flags] --python scripts/qualify_cloth_lod.py --
  --source ORIGINAL.blend --candidate NEW_LOD/source.blend --capture CAPTURE_DIR --output NEW_POSE_CHECK
blender [flags] --python scripts/author_stytch_cloth.py --
  --source NEW_LOD/source.blend --lod-report NEW_LOD/lod.json
  --pose-report NEW_POSE_CHECK/fidelity.json --draft-authoring --output NEW_BUNDLE
```

The optional feedback names exact frozen source vertices from a retained failed
pose report. It is bounded to 2,048 vertices; it cannot change the thresholds.
Authoring freezes whole polygon owners and landmark vertices against the source
fingerprint. Export consumes that frozen file with `--authoring` instead of
`--draft-authoring`; it never reruns a classifier. The fixture-specific planes
are design choices and do not derive physical ownership from positive weights.
All outputs require a new directory. Failed output is retained, not overwritten.

For the self-contained public candidate, the original high-resolution native
source and private captures are unnecessary:

```text
blender [flags] --python tests/blender_cloth_authoring.py
blender [flags] --python scripts/qualify_cloth_modular.py --
  --fixture example/v2/modular/StytchDummyCloth --output NEW_PUBLIC_CHECK
blender [flags] --python scripts/render_cloth_lod.py --
  --reference example/v2/generated/StytchDummyCloth/character.glb
  --candidate example/v2/modular/StytchDummyCloth/character.glb --output NEW_RENDERS
```

Open `source.blend` to edit the authoritative whole source and inspect its
face ownership. Use **Export Authored Source (No Rebuild)** to re-export. Do not
modify the frozen example: copy it and re-author the ownership when geometry
changes. Source-authority preservation is checked independently of GLB fidelity.

## Capture protocol and attribution

`audit_cloth_replay.py` requires `stytch.cloth-native-replay.v1`, explicit matrix
layout and complete parent-local poses, named/parented native rests, inverse
bind slots, complete mesh/skeleton ancestors, imported arrays and GPU-baked
arrays. It checks the asset and capture SHA chain, every imported reversed
winding, joint slots and native/raw oriented triangle multiplicity. It never
guesses an old index-only pose file's axes, order or normalization.

On the supplied eight captures, native versus raw LBS positions differ by at
most 0.882 micrometres; raw versus GPU by 9.774 micrometres; direct LBS normals
versus GPU by 0.0138 degrees. Imported weight quantization is reported, not
renormalized away. Blender's geometric normals differ substantially from these
transported normals, so a smooth DCC preview alone cannot clear the source.

This finds no position/direct-normal transport disagreement on those samples.
It does not attribute all folds to weights alone or prove the pose adapter is
correct in every scenario. Source geometry, skin and target interaction still
needs visual and consumer review. App screenshots, code and dense captured
buffers are external inputs; public reports contain only numerical results and
provenance hashes. No pixel equality with private app captures is claimed.
