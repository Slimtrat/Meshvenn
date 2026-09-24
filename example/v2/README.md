# GLB reference examples V2

Seven open-content GLB files from [Khronos glTF Sample Assets](https://github.com/KhronosGroup/glTF-Sample-Assets), pinned to the upstream revision in `manifest.json`. These are **reference assets for development and CI**, not part of the Blender extension package.

The geometry cases are Avocado, BarramundiFish, BoomBox and ToyCar. The rig cases are RiggedSimple, RiggedFigure and Fox. ToyCar includes material extensions and cameras; Fox is a quadruped and must not be treated as a Canonical Biped V1 success case.

The asset bytes, SHA-256 hashes and glTF structure are checked by `tests/test_v2_assets.py`. Blender CI imports all seven files and benchmarks the four static geometry assets. Each source GLB is rendered into ten 2D views, which alone feed the native reconstruction. The report measures silhouette IoU (minimum 0.65), plus a symmetric 3D surface Chamfer and F-score (minimum 0.60 at a distance of 5% of the longest model extent). A shape-proportion error above 0.25 also fails CI. The 3D comparison centres each model and normalizes its longest dimension, but never rotates or ICP-aligns it. Empty input views score zero.

The rig benchmark uses RiggedFigure's geometry with its original armature stripped off. Canonical Biped V1 sees only this unrigged mesh; the source skeleton is reserved for scoring 17 corresponding joint positions. CI also checks 100% skin coverage, at most four influences per vertex, normalized weights, localized pose deformation, and GLB export/import preservation. The accepted mean joint-head error is at most 0.15 model heights; the maximum individual error is 0.20. RiggedSimple and Fox remain import/animation cases, not Canonical Biped success fixtures.

The character end-to-end case closes the gap between those separate benchmarks: it exports a structurally verified unrigged rest mesh, renders ten views, reconstructs the mesh from pixels, generates a fresh canonical rig, authors a deterministic validation action, and verifies the skin plus animation after GLB export/import. Its measured gates are IoU 0.65, surface F-score 0.85, maximum normalized extent error 0.25, mean joint error 0.10 and worst joint error 0.16. The intermediate GLB must contain exactly zero armatures, animations and vertex groups.

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

## Reproduce the benchmark

With Blender and the native library available:

```sh
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_glb_v2.py -- --asset avocado --output output/v2-benchmark
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_rig_v2.py -- --output output/v2-rig
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_character_v2.py -- --output output/v2-character
```

The geometry output contains source and reconstructed sheets, the generated GLB, and `report.json` with both silhouette and 3D surface measurements. Rig and character outputs contain their own reports plus exportable GLBs; the character artifact includes a three-key animation verified after reimport. CI thresholds are regression gates, not a claim that silhouettes fully recover an object's 3D shape or that this rig is production-ready for every character.
