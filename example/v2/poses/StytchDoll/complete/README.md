# Nineteen synchronized Stytch poses

`index.json` pins Stytch revision `1c9040e51be1e757c974eca794604cb9553cb532`
and the accepted doll GLB `76590fd9…bcb57`. Each case includes an authorized
native probe plus a redundant matrix proof. The source JSON SHA-256, Git blob
and synchronized private PNG SHA-256 provide provenance. **Private PNGs are not
published.** Semantic controls, mount loadouts, ancestor node names and world
telemetry are excluded; no consumer code is included.

The native probe retains the exact numeric `Rest`/`Pose` values and parent indices.
Pose is the **complete parent-local transform**, not a rest-relative delta.
The companion file retains numeric `RestRelative`, `SkeletonSpace` and ancestor
local/world matrices. All are basis columns X/Y/Z plus origin, with the implicit
last row `[0,0,0,1]`. Recomposition is validated before projecting any files.
Its `2e-4` captured-float32 tolerance is separate from unchanged export gates.

Cases:

- Hall, held (`lift=.75`, `wobble=.4`) and Hall with the left leg hidden.
- Three distinct Standard Stable / Walk frames, all five regions visible.
- Twelve distinct Mono Leg / Hop frames with the right leg hidden. CyclePhase
  is the recorded animation lane phase, **not a physical-contact assertion**.
- World one-leg transit, right arm and leg hidden. Its movement intent is a
  **Walk approach**, not an explicit Hop despite the original filename.

## Replay

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/replay_stytch_pose_series.py -- --output /tmp/stytch-series
```

All nineteen cases independently compare the full original native mesh before
partitioning, stored GLB linear-blend skinning, and Blender reimport. Region
visibility is applied separately to actual modular nodes, never mistaken for
different bone input. Rest hierarchy/frames, exact input fingerprints and source
authority are checked for every case. External facing/world transforms are
validated in the matrix proof, not applied a second time to skin evaluation.

`../series-replay/series.json` records the complete local run. Ten PNGs for held,
walk-02 and hop-11 are **our own Blender renders**. All three calculations agree
within 1.1 micrometres, but torso deformation remains unacceptable. The frozen
torso cohort has 783–1,234 edges outside ±20% length change across these inputs.
This establishes an upstream skin defect across the supplied motion samples;
it does not certify all consumer adapter targets or exact screenshot pixels.

CI regenerates all nineteen cases with current commit/run/attempt metadata and
uploads separate evidence. The committed local run is not passed off as a CI run.
The head-isolation candidate remains separate, with unchanged native rests and
its own fingerprint; it does not resolve torso/neck quality or Stytch acceptance.
#60 stays open. No wound caps, private game behavior or physical ABI are introduced.
