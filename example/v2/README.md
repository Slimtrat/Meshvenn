# GLB reference examples V2

Ten open-content GLB files from [Khronos glTF Sample Assets](https://github.com/KhronosGroup/glTF-Sample-Assets), [three.js](https://github.com/mrdoob/three.js) and [Quaternius](https://quaternius.com/), pinned to exact upstream repository revisions in `manifest.json`. These are **reference assets for development and CI**, not part of the Blender extension package.

The geometry cases are Avocado, BarramundiFish, BoomBox and ToyCar. The rig cases are RiggedSimple, RiggedFigure, Fox, RobotExpressive, QuaterniusHuman and UAL1_Standard. ToyCar includes material extensions and cameras. Fox is a quadruped: it verifies explicit source-role adaptation, but remains excluded from Canonical Biped anatomical-fit scoring. RobotExpressive is the multi-mesh humanoid stress case with fourteen clips. QuaterniusHuman tests the Mixamo-compatible adapter with seven authored clips. UAL1 tests the Unreal-compatible adapter with 43 authored clips, including four fixed poses: A_TPose, Pistol_Aim_Down, Pistol_Aim_Neutral and Pistol_Aim_Up. The latter are independently checked against source keyframe data and must stay constant; all other clips must move. No Adobe Mixamo downloads or Epic Mannequin assets are redistributed.

The asset bytes, SHA-256 hashes and glTF structure are checked by `tests/test_v2_assets.py`. Blender CI imports all ten files and benchmarks the four static geometry assets. Each geometry source GLB is rendered into ten 2D views, which alone feed the native reconstruction. The report measures silhouette IoU (minimum 0.65), plus a symmetric 3D surface Chamfer and F-score (minimum 0.60 at a distance of 5% of the longest model extent). A shape-proportion error above 0.25 also fails CI. The 3D comparison centres each model and normalizes its longest dimension, but never rotates or ICP-aligns it. Empty input views score zero.

The rig benchmark exports a rest-geometry GLB with zero skins/actions/groups, deletes all source objects, armature datablocks and actions, then runs that file through the product INPUT/GEOMETRY/RIG path. Only scoring retains reference joint positions and arm-region labels; the fitter cannot access the source rig or weights. UVs/materials survive the neutral export. CI keeps V1 as a baseline and gates V2 on three humanoids with explicit 17-role source correspondences:

| Unrigged input derived from | Maximum mean / worst joint error (model heights) | Maximum mean unrelated arm weight | Maximum six-leg-joint mean / worst error | Maximum mean unrelated leg weight |
| --- | --- | --- | --- | --- |
| RiggedFigure | 0.02 / 0.04 | 0.08 | 0.005 / 0.01 | 0.02 |
| QuaterniusHuman | 0.035 / 0.07 | 0.015 | 0.018 / 0.03 | 0.025 |
| UAL1_Standard | 0.04 / 0.09 | 0.02 | 0.025 / 0.04 | 0.10 |

The `--check-pose-quality` gate runs 16 isolated bilateral world-axis probes: shoulders ±60° around Y/Z, hips ±60° around X and ±35° around Y. Within a radius of 12% of model height around each fitted joint, it measures unique surface-edge length ratios. The nearest-rank p95 of `abs(log(posed_length / rest_length))` treats compression and stretch equally; the worst single edge is also gated. Coincident UV seams do not inflate samples, degenerate rest edges are excluded, and collapsed posed edges are retained. Budgets below are regression limits for these pinned fixtures, not universal suitability thresholds:

| Fixture | Worst-pose p95 / worst absolute log ratio | Maximum collapsed fraction (ratio < 0.25) | Maximum stretched fraction (ratio > 2) |
| --- | --- | --- | --- |
| RiggedFigure | 0.43 / 0.65 | 0 | 0 |
| QuaterniusHuman | 1.18 / 1.65 | 0.018 | 0.022 |
| UAL1_Standard | 0.40 / 1.95 | 0.002 | 0.002 |

The independent `--check-hinge-quality` gate adds 24 bilateral elbow/knee stress poses: forearms ±45°/±90° around world Y/Z, shins ±45°/±90° around world X. Its local edge measurements retain edges with at least one endpoint within 12% of height from the fitted joint, including transitions between vertex rings in coarse meshes. Edges with both endpoints outside are excluded. The original shoulder/hip edge selection and budgets remain unchanged.

| Fixture | Hinge worst-pose p95 / worst absolute log ratio | Maximum collapsed / stretched fractions |
| --- | --- | --- |
| RiggedFigure | 0.35 / 0.36 | 0 / 0 |
| QuaterniusHuman | 0.39 / 0.58 | 0 / 0 |
| UAL1_Standard | 0.395 / 0.63 | 0 / 0 |

All 24 poses must pass on both generated and reimported rigs, with the same localized-movement and matching-probe tolerances as the shoulder/hip suite. V2 smoothly suppresses nonadjacent influences near elbows/knees and broadens the adjacent-bone distance kernel there; only an available region can supply a hinge prior, overlapping priors select one neighbourhood, and the ambiguous midline keeps its fallback. Linear GLB skinning still compresses deep bends: zero edges below a length ratio of 0.25 does not mean zero compression or preserved volume. The ± stress directions are not anatomical range-of-motion certification.

The independent `--check-combined-quality` gate adds 36 parent-first world-axis stress poses (80 joint observations): 32 bilateral signed shoulder+elbow or hip+knee combinations, plus four same-side arm+leg combinations. Cases include coplanar bends, cross-plane bends, opposing rotations and partial bends. Each joint is measured separately using the existing root/hinge edge selectors; one bad joint cannot disappear in a pooled mean. Every active limb must move at least 0.01 heights and every inactive limb at most 0.0005, including the other limb family in single-chain cases. All cases, joints and four limb responses must exist, be finite and agree with the recomputed worst-case summary.

| Fixture | Combined worst-pose p95 / worst absolute log ratio | Maximum collapsed / stretched fractions |
| --- | --- | --- |
| RiggedFigure | 0.56 / 0.67 | 0 / 0 |
| QuaterniusHuman | 0.90 / 1.18 | 0 / 0.022 |
| UAL1_Standard | 0.40 / 1.30 | 0 / 0.002 |

These are separate regression budgets for the new stress set, not relaxed isolated-pose budgets. In addition to per-joint metrics (0.005 tolerance, exact edge counts) and per-limb movement (0.0001 heights), reimport must reproduce each sampled posed position within 0.0001 heights. A deterministic rest-position reference deduplicates seams and samples globally and near eight joints, up to 80 vertices. Reimport matches the same rest positions, independent of vertex ordering; missing samples or changed references fail. This sampled fidelity check does not certify every vertex or the surface between samples. Full pose bases and rotation modes are restored on success or failure, and invalid multi-bone requests fail before mutation.

V2 transfers distant shin/foot score mass to the corresponding thigh near the hip, preserving the pre-pruning leg-chain total and leaving raw arm/axial scores unchanged. The fade is capped by femur length so short limbs retain knee influences. This targets combined-bend hip artifacts hidden by isolated thigh rotations. Against the previous hinge-blend revision, RiggedFigure's combined worst p95 decreases from 0.6594 to 0.5347. The other fixtures do not improve uniformly: Human's worst edge changes from 1.1323 to 1.1359; UAL1 has one of 761 hip edges above ratio 2 in its worst stretched-fraction case (0.001314), previously zero in this combined set. These limitations remain visible and bounded; none of the 40 isolated-pose budgets changed. V1 and default AUTO routing are unchanged; V2 remains opt-in.

Every probe also requires mean motion of its source-labelled limb of at least 0.01 model heights and mean opposite-limb motion at most 0.0005. Both generated and reimported rigs must pass. Matching world-axis probes must retain displacement within 0.0001 heights, edge counts exactly, and individual edge-summary measurements within 0.005; this avoids dependence on importer-specific bone rolls. Pose basis/modes are restored even on diagnostic failure. The score does not measure volume loss, triangle intersections, collisions, anatomical correctness or motions outside the tested poses. Wider V2 shoulder/hip transitions reduce abrupt weight changes; this does not eliminate all compression. V1 remains an ungated pose-quality baseline, and default routing is unchanged.

Each V2 case also requires 100% skin coverage, at most four normalized influences, localized arm and leg deformation before/after reimport and fail-before-publish export fidelity. Limb-region labels come only from confident source weights (at least 70% on that limb's descendants); mean and worst leakage are reported, and only the mean is gated. V2 measures independent arm trajectories and local depth, ignores duplicate UV-seam positions and binds regions using fitted joints. Dense non-humanoid blocks are rejected cleanly, and an injected post-binding failure verifies rollback of user data. Fox remains a quadruped preservation fixture, never a successful canonical biped fit.

Lower-body fitting uses closed triangle/plane sections, not vertex density. Foot-to-leg narrowing and a calf/thigh narrowing or supported centreline bend provide ankle/knee cues. A 0.95 femur/tibia length prior estimates hip height from those cues, with a surface-consistency check and bilateral agreement; this is not anatomical inference. Missing topology, open sections, featureless legs and conflicting hips explicitly fall back. Observations within 1% of height retain stable anchors; the report separates observed cues from applied anchors, and arm confidence from leg evidence. The pelvis retains its canonical height unless bilateral hip estimates require raising it; other axial heights remain priors. These three V2 fixtures must expose bilateral cues, so silently reverting to fixed heights cannot satisfy CI. V1's new leg measurements are diagnostic unless the explicit leg-gate flags are supplied; it keeps its existing acceptance behavior.

The Motion smoke builds a fresh Canonical Biped V2 target, retargets RiggedFigure's real source action across 17 semantic roles, requires non-constant bone and vertex motion, routes the result through GLB Export V1, and verifies the action after reimport. RiggedSimple is an explicit clean-rejection fixture: its two generic bones are insufficient for the canonical profile and must not leak imported data or mutate the target.

The character end-to-end case closes the gap between those separate benchmarks: it exports a structurally verified unrigged rest mesh, renders ten views, reconstructs the mesh from pixels, generates a fresh canonical rig, retargets the real source action through the Motion stage, publishes it through GLB Export V1, and verifies the skin plus animation after reimport. Its shared geometry gates are IoU 0.65, surface F-score 0.85 and maximum normalized extent error 0.25. The V1 joint gates remain 0.10 mean / 0.16 worst; the V2 A/B gates are 0.08 / 0.14. The intermediate GLB must contain exactly zero armatures, animations and vertex groups.

The direct GLB-first gate is independent from image reconstruction. AUTO preserves RiggedFigure, Fox and RobotExpressive (1, 3 and 14 clips), including the robot's morph animation. Canonicalization remains explicit for supported humanoids; Fox is rejected by Canonical Biped. RiggedSimple falls back to geometry-only with explicit rig/animation-loss warnings; ToyCar is static. Every AUTO case enables fail-before-publish export-reimport validation and publishes separate completeness and export-fidelity results. The latter checks rest geometry, five matching samples per clip, normalized skin weights, hierarchy, durations, morph count and sampled PBR materials/textures. No reimport evidence means no fidelity score. Rig/Motion do not penalize a deliberately static route, and completeness never hides a degraded route's losses. UI timeline frames are restored; source GLBs cannot be overwritten even with the overwrite option enabled.

AUTO also preserves QuaterniusHuman and UAL1_Standard without losing their clips. Both direct preservation and AUTO are exercised by V2 CI, and AUTO runs against the built extension package too. Their profile labels certify this sampled preservation route, not canonical retargeting or imports into Adobe/Epic products. Pure tests bind every E2E profile to actual skin-joint names from its checked-in fixture.

These surface and joint metrics measure real 3D output, but do not certify hidden interiors, watertight volume or animation retargeting quality.

## Licensing and attribution

Each model has its own license; the repository's code license does not replace it. The original license notices are linked below. Keep these credits when redistributing the V2 examples:

| Model | License | Credit and original notice |
| --- | --- | --- |
| Avocado | CC0-1.0 | [Microsoft](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/c6a6bd13ab2b3c685c7903d03561b8a9392f38b8/Models/Avocado/README.md) |
| BarramundiFish | CC0-1.0 | [Microsoft](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/c6a6bd13ab2b3c685c7903d03561b8a9392f38b8/Models/BarramundiFish/README.md) |
| BoomBox | CC0-1.0 | [Microsoft](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/c6a6bd13ab2b3c685c7903d03561b8a9392f38b8/Models/BoomBox/README.md) |
| ToyCar | CC0-1.0 | [Guido Odendahl and Eric Chadwick](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/c6a6bd13ab2b3c685c7903d03561b8a9392f38b8/Models/ToyCar/README.md) |
| RiggedSimple | CC-BY-4.0 | [Cesium](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/c6a6bd13ab2b3c685c7903d03561b8a9392f38b8/Models/RiggedSimple/README.md) |
| RiggedFigure | CC-BY-4.0 | [Cesium](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/c6a6bd13ab2b3c685c7903d03561b8a9392f38b8/Models/RiggedFigure/README.md) |
| Fox | CC0-1.0 (model), CC-BY-4.0 (rig, animation, conversion) | [PixelMannen, tomkranis, AsoboStudio and scurest](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/c6a6bd13ab2b3c685c7903d03561b8a9392f38b8/Models/Fox/README.md) |
| RobotExpressive | CC0-1.0 | [Tomás Laulhé and Don McCurdy](https://github.com/mrdoob/three.js/blob/b924f0cad4058dc4dde71445c796980c3cd5b5ed/examples/models/gltf/RobotExpressive/README.md) |
| QuaterniusHuman | CC0-1.0 | Quaternius (model, rig, animations); Jatin Rana (glTF conversion). [Upstream model notice](https://github.com/rana-jatin/avatar-stage/blob/142459752be51221af80c0c2df418bfbb66f1e5e/demo/public/models/MODEL_LICENSE.md) |
| UAL1_Standard | CC0-1.0 | [Quaternius Universal Animation Library](https://quaternius.com/packs/universalanimationlibrary.html); bytes pinned from the [public mirror](https://github.com/NafisRayan/Animate-Rigged-Humanoid-No-Blender/tree/5821923af517ac5fdc82505faa92a0d575fc1b1a/Universal%20Animation%20Library%5BStandard%5D) |

## Reproduce the benchmark

With Blender and the native library available:

Append `--check-pose-quality --check-hinge-quality --check-combined-quality` to each V2 rig command below to enforce the fixture-specific 16+24+36 pose budgets and sampled deformation fidelity as CI does. Rig-only tests do not require the native reconstruction library.

```sh
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_glb_v2.py -- --asset avocado --output output/v2-benchmark
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_rig_v2.py -- --output output/v2-rig
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_rig_v2.py -- --implementation canonical-biped-v2 --require-observed-leg-cues --check-leg-deformation --max-mean-leg-joint-error 0.005 --max-leg-joint-error 0.01 --max-leg-unrelated-weight 0.02 --output output/v2-rig-canonical-v2
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_rig_v2.py -- --implementation canonical-biped-v2 --asset quaternius_human --max-mean-joint-error 0.035 --max-joint-error 0.07 --max-arm-unrelated-weight 0.015 --require-observed-leg-cues --check-leg-deformation --max-mean-leg-joint-error 0.018 --max-leg-joint-error 0.03 --max-leg-unrelated-weight 0.025 --output output/v2-rig-human
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_rig_v2.py -- --implementation canonical-biped-v2 --asset quaternius_ual1 --max-mean-joint-error 0.04 --max-joint-error 0.09 --max-arm-unrelated-weight 0.02 --require-observed-leg-cues --check-leg-deformation --max-mean-leg-joint-error 0.025 --max-leg-joint-error 0.04 --max-leg-unrelated-weight 0.10 --output output/v2-rig-ual1
blender --background --factory-startup --python-exit-code 1 --python tests/blender_glb_export_smoke.py -- --package-root . --output output/v2-export
blender --background --factory-startup --python-exit-code 1 --python tests/blender_motion_smoke.py -- --output output/v2-motion
blender --background --factory-startup --python-exit-code 1 --python tests/blender_glb_first_pipeline_smoke.py -- --package-root . --input example/v2/assets/RiggedFigure.glb --static-input example/v2/assets/ToyCar.glb --unsupported-input example/v2/assets/RiggedSimple.glb --output output/v2-glb-first
blender --background --factory-startup --python-exit-code 1 --python tests/blender_glb_first_pipeline_smoke.py -- --package-root . --input example/v2/assets/RobotExpressive.glb --expected-profile threejs-robot-expressive-v1 --expected-animations 14 --output output/v2-glb-first-robot
blender --background --factory-startup --python-exit-code 1 --python tests/blender_glb_first_pipeline_smoke.py -- --package-root . --input example/v2/assets/Fox.glb --expected-profile khronos-fox-v1 --expected-animations 3 --output output/v2-glb-first-fox
blender --background --factory-startup --python-exit-code 1 --python tests/blender_glb_auto_route_smoke.py -- --package-root . --input example/v2/assets/QuaterniusHuman.glb --expected-route preserve-source --expected-profile mixamo-humanoid-v1 --expected-animations 7 --output output/v2-auto-mixamo
blender --background --factory-startup --python-exit-code 1 --python tests/blender_glb_auto_route_smoke.py -- --package-root . --input example/v2/assets/UAL1_Standard.glb --expected-route preserve-source --expected-profile unreal-mannequin-v1 --expected-animations 43 --static-clip A_TPose --static-clip Pistol_Aim_Down --static-clip Pistol_Aim_Neutral --static-clip Pistol_Aim_Up --output output/v2-auto-unreal
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_character_v2.py -- --output output/v2-character
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_character_v2.py -- --rig-implementation canonical-biped-v2 --output output/v2-character-canonical-v2
```

The geometry output contains source and reconstructed sheets, the generated GLB, and `report.json` with both silhouette and 3D surface measurements. Export, Rig, Motion and character outputs contain their own reports plus GLB artifacts. GLB Export V1 records container structure, byte size and SHA-256; the character artifact includes the retargeted source action verified after reimport. CI thresholds are regression gates, not a claim that silhouettes fully recover an object's 3D shape, that every external renderer reproduces Blender exactly, or that this rig and retarget profile are production-ready for every character.
