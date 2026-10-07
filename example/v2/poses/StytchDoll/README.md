# Exact consumer Hall pose — issue #60

`factory-hall-pose.json` is the authorized, byte-preserved Stytch snapshot for
the accepted `../../modular/StytchDoll` GLB. `provenance.json` pins its private
source revision, Git blob, SHA-256 and serialization. No private application
screenshots or consumer implementation are included.

The supplied one-leg JSON has identical bytes. The hidden-left-leg render tests
visibility with the same Hall pose; it does not qualify hop motion. Held, walk
and one-leg-hop matrices were missing at that revision and are still required
for complete issue #60 triage.

## Replay without reconstructing the character

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/replay_stytch_doll_pose.py -- \
  --pose example/v2/poses/StytchDoll/factory-hall-pose.json \
  --hidden-region left-leg --output /tmp/stytch-hall-replay
```

The runner accumulates parent-local transforms, converts the world coordinate
frame once, and derives pose deltas from the captured rest. It applies these
deltas to the original native armature and to the reimported modular GLB. An
independent CPU calculation evaluates the stored GLB positions, skin weights
and inverse binds, retaining ancestor normalization exactly once.

`replay/` contains **Meshvenn's own Blender renders**, not Stytch captures.
The frozen torso cohort is source-rest `Z/height in [0.45,0.67]` and lateral
distance/height <= 0.14. Source/native, decoded GLB and reimported GLB agree to
less than one micrometre, while the same upstream head/torso collapses remain
visible before partitioning. This establishes an upstream skin defect for this
provided pose; it does not prove every adapter target or animation correct.

The accepted baseline is unchanged. The separate head-isolation candidate has
its own fingerprint and bounded head probes; it is not passed off as a complete
Hall/torso/neck fix or as Stytch consumer acceptance.
