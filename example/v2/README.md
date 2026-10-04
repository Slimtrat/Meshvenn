# GLB reference examples V2

Ten open-content GLB files from [Khronos glTF Sample Assets](https://github.com/KhronosGroup/glTF-Sample-Assets), [three.js](https://github.com/mrdoob/three.js) and [Quaternius](https://quaternius.com/), pinned to exact upstream repository revisions in `manifest.json`. These are **reference assets for development and CI**, not part of the Blender extension package.

The geometry cases are Avocado, BarramundiFish, BoomBox and ToyCar. The rig cases are RiggedSimple, RiggedFigure, Fox, RobotExpressive, QuaterniusHuman and UAL1_Standard. ToyCar includes material extensions and cameras. Fox is a quadruped: it verifies explicit source-role adaptation, but remains excluded from Canonical Biped anatomical-fit scoring. RobotExpressive is the multi-mesh humanoid stress case with fourteen clips. QuaterniusHuman tests the Mixamo-compatible adapter with seven authored clips. UAL1 tests the Unreal-compatible adapter with 43 authored clips, including four fixed poses: A_TPose, Pistol_Aim_Down, Pistol_Aim_Neutral and Pistol_Aim_Up. The latter are independently checked against source keyframe data and must stay constant; all other clips must move. No Adobe Mixamo downloads or Epic Mannequin assets are redistributed.

The asset bytes, SHA-256 hashes and glTF structure are checked by `tests/test_v2_assets.py`. Blender CI imports all ten files and benchmarks the four static geometry assets. Each geometry source GLB is rendered into ten 2D views, which alone feed the native reconstruction. The report measures silhouette IoU (minimum 0.65), plus a symmetric 3D surface Chamfer and F-score (minimum 0.60 at a distance of 5% of the longest model extent). A shape-proportion error above 0.25 also fails CI. The 3D comparison centres each model and normalizes its longest dimension, but never rotates or ICP-aligns it. Empty input views score zero.

The rig benchmark uses RiggedFigure's geometry with its original armature stripped off. Each canonical implementation sees only this unrigged mesh; the source skeleton is reserved for scoring 17 corresponding joint positions. CI keeps the V1 baseline and independently gates Canonical Biped V2 at a mean joint-head error of 0.06 model heights and a maximum error of 0.10. It also checks 100% skin coverage, at most four influences per vertex, normalized weights, localized pose deformation, and GLB export/import preservation. V2 reports its envelope-fit evidence and uses deterministic regional binding. Fox remains a quadruped import/animation case, not a canonical-biped success fixture.

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

```sh
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_glb_v2.py -- --asset avocado --output output/v2-benchmark
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_rig_v2.py -- --output output/v2-rig
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_rig_v2.py -- --implementation canonical-biped-v2 --output output/v2-rig-canonical-v2
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
