# Captured articulation coverage

This review measures which native joints the nineteen exact shoulder-aligned
Stytch captures actually rotate. It complements the
[strict transport replay](README.md); it does not change the doll, a pose or the
consumer. The machine-readable report is `articulation-coverage.json`.

| Provenance | SHA / revision |
| --- | --- |
| Report | `d4ba40a81a76d51d16781bfd235207ce3882dd6eb6e3c2853f229c7c1ee6fa61` |
| Generator code | `b7ad38be0633454c3ddcc140b84ca6ec09514b33` |
| Captured pose index | `e2285869ae4e5237791ada40bc1b0cc6253d324c120aad1b97e1fb9b7d2ead32` |
| Stytch revision | `a760e57a08d526088632b8cd269c391deeb3ecfb` |

The current captures move the upper arms but leave both forearms essentially at
their native rest-relative rotation (below 0.0001 degree). A hand moving through
space because its shoulder moves is not evidence that its elbow bends correctly.

| Native joint | Present captures | Maximum visible local rotation | Visible captures at least 5 degrees |
| --- | ---: | ---: | ---: |
| `forearm.L` | 19 | < 0.0001° | 0 |
| `forearm.R` | 18 | < 0.0001° | 0 |
| `thigh.L` | 18 | 120.742° | 17 |
| `thigh.R` | 6 | 40.066° | 3 |
| `shin.L` | 18 | 67.409° | 16 |
| `shin.R` | 6 | 12.355° | 2 |

The right knee's overall maximum is about 45.202 degrees in
`World-03-one-leg-hop`, where the right leg is absent. It remains recorded but
does not earn visible knee credit. Likewise, the hidden right thigh reaches
about 119.576 degrees without qualifying that absent leg's silhouette.

## Measurement and limits

For each native joint, use `inverse(Rest) * Pose` to remove its native rest frame.
The report measures this **local delta**, not the accumulated skeleton/world
matrix. The 5-degree threshold is an explicit amplitude inventory setting, not
an anatomical range, a deformation tolerance or a universal acceptance criterion.
One excited frame does not establish range, direction, continuity or useful
combined posing. The current visible knee samples do not certify all knee bends.

Rotation uses the skew/trace `atan2` angle for near-rigid deltas. A trace-only
`acos` would invent small angles from float32 rest noise. Scale/shear deltas are
reported separately and cannot earn rotation credit; translations retain the
capture's own units. External ancestor squash/facing remains outside local joint
excitation. Existing matrix-proof and source/raw/reimport tolerances are intact.
Diagnostic rounding follows all unrounded eligibility/excitation decisions and
has a Python 3.11/3.13 arithmetic regression check.

Both profiles retain their own index, asset and nineteen probe/proof fingerprints.
Every byte fingerprint, path, hierarchy, matrix recomposition and presence list
is checked before reports or replay output is created. The shared preflight
also serves the existing Blender series replay. No private screenshots, controls,
world telemetry or consumer code are copied into this report.

`visible_rotation_excitation_complete=false`, `visual_qualification=false` and
`consumer_acceptance=false` are expected for the current evidence. They are
separate from the successful transport result. No geometry, skin, native rest,
material, region, socket or clip is changed by this review. Earlier source,
capture-index and pinned replay bytes remain immutable.

## Required next evidence

The request below is historical. The subsequent
[selected distal-skin capture set](../StytchDollDistalChains/README.md) now supplies
the exact delivered asset's nineteen production poses and four visible elbow
excitations. Its context summaries still expose unexercised Walk/held forearms.
This older pinned inventory and its captured target remain unchanged.

Select the exact [distal-chain candidate](../../modular/StytchDollDistalChains/README.md)
in Stytch before capturing a new successor series. The existing captures still
target `6654f85a...`; they do not qualify candidate `58bb85ca...` merely because
its rests are unchanged. Retain the complete synchronized matrices, numeric
ancestor proofs, recorded presence and selected-artifact fingerprint.

For elbow qualification, add actual visible left/right forearm flexions near
45 and 90 degrees, plus a useful combined held/walk pose. Keep the existing
isolated bilateral ±45/±90 probes as controls; never relabel generated probes as
consumer captures. Further source changes must improve the intended poses while
retaining the documented isolated-collapse controls. Hip/knee extremes, source
joint fit, consumer world squash and artistic acceptance remain unresolved.
The local centering/support experiments were rejected because some worst folds
increased despite improved aggregate strain. They are not delivered candidates.

Reproduce the report without Blender into a fresh path:

```bash
python scripts/report_stytch_pose_coverage.py \
  --profile shoulder-aligned --source-sha <exact-code-commit> \
  --output /tmp/shoulder-articulation-coverage.json
python scripts/report_stytch_pose_coverage.py \
  --profile original --source-sha <exact-code-commit> \
  --output /tmp/original-articulation-coverage.json
```

V2 CI includes both reports and a read-only job summary in the existing
`stytch-head-isolation-*` artifact. Future `series.json` reports embed the same
joint-motion inventory. The historical pinned `replay/series.json` remains a
generation-time record and is not rewritten. Issues #60 and #63 remain open;
engine/rig/format expansion stays paused.
