# meshvenn-humanoid

An opt-in humanoid deformation supervisor around Meshvenn. The engine does not import this package. Its base API imports only the Python standard library; Blender adapters load only in a configured Blender host.

The native profile recognizes the eighteen-joint hierarchy and bilateral weighted head/limb support of a static source. It evaluates exported, reimported GLBs with shoulder and elbow poses. A misplaced forearm influence cannot pass simply because it produces a smooth surface: proximal and distal link rigidity are measured separately from collar radius, triangle-area retention and inverted faces. Geometry, UVs, native rest frames, weights, export fidelity, texture/material transport and protected points are also checked. Surface/topology observations and saved appearance diagnostics run automatically and remain separate from anatomical or artistic acceptance.

The bounded loop keeps an immutable baseline, regenerates local arm weights, reevaluates each candidate, rejects regressions and saves its journal after every transition. Unknown or failed checks cannot select a result. The limits are frozen before the first attempt. Resume requires the same source hash and policy; elapsed budget is not reset. A previously passing GLB is retained byte for byte. No source file is overwritten.

```sh
python -m pip install packages/meshvenn_humanoid
meshvenn-humanoid --blender /trusted/blender --engine-root /trusted/Meshvenn --source mannequin.glb --output output/humanoid-run
```

The source can be a GLB or a `.blend` with one native static mesh, or an explicit `--object`. Output contains `session.json`, per-candidate receipts/measurements, editable Blender sources and a `selected.glb` only when the profile checks pass. Use `--resume` for interrupted sessions. Cancellation and time/attempt/stagnation budgets preserve the source and retained candidates.

For an embedded engine or agent, construct `HumanoidLoop(trusted_port, workspace, budget=Budget(...))`. The host port owns detection, regeneration, export, measurement and artifact verification. File paths, Blender executables and code/providers are host configuration, not model-supplied actions. This package makes no paid generation calls.

`integration.Binding(registry, supervisor)` decorates the existing `canonical-biped-v2` implementation without changing its native contract. Enabling the separate **Meshvenn Humanoid Quality** Blender extension installs this decorator. Checks then run automatically after fitting a new Canonical V2 rig, before the pipeline proceeds. Passing weights are applied transactionally to the same mesh and armature. Disabling/unregistering the extension restores the original implementation.

The profile does not claim general humanoid recognition, aesthetic quality, watertightness or Stytch acceptance. Its surface/appearance reports can expose unresolved findings; successful deformation checks are not a general character certificate. Unsupported animated, constrained, non-native or ambiguous sources are retained without an inferred repair. Stronger visual/topology policies require their own measured criteria and regeneration ports; they must not be silently treated as passing.

Run tests with `python -m unittest discover -s packages/meshvenn_humanoid/tests`. Real Blender/GLB regeneration and pipeline integration are exercised separately on the pinned generated dummy fixture. The fixture is not a known 3D ground truth.
