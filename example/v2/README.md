# GLB reference examples V2

Seven open-content GLB files from [Khronos glTF Sample Assets](https://github.com/KhronosGroup/glTF-Sample-Assets), pinned to the upstream revision in `manifest.json`. These are **reference assets for development and CI**, not part of the Blender extension package.

The geometry cases are Avocado, BarramundiFish, BoomBox and ToyCar. The rig cases are RiggedSimple, RiggedFigure and Fox. ToyCar includes material extensions and cameras; Fox is a quadruped and must not be treated as a Canonical Biped V1 success case.

The asset bytes, SHA-256 hashes and glTF structure are checked by `tests/test_v2_assets.py`. The Blender CI imports all seven files, checks mesh, armature and animation data, and benchmarks all four static geometry assets. Each benchmark renders the source GLB into a ten-view projection sheet, reconstructs it with the native engine, renders the result and reports per-view silhouette IoU. The source GLB is never passed to reconstruction. A mean IoU below 0.65 fails CI; invalid or empty input views score zero.

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
```

The output contains source and reconstructed sheets, the generated GLB, and `report.json`. The CI uses a conservative smoke threshold; the reported IoU is a measurable baseline, not a claim that the underlying 3D shape is fully recovered from silhouettes.
