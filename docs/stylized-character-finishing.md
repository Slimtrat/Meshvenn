# Finishing a generated-view character

Keep the generated images, registered camera manifest and the first reconstructed Blender source. Run appearance and rig trials against that same source surface. The benchmark refuses a changed source SHA256 and checks that every trial preserves the original vertices, polygons and UV coordinates.

## Arm fitting

Canonical Biped V2 distinguishes A- and T-pose arms from their observed lateral trajectory. A nearly horizontal arm remains a T-pose when a large head lowers the shoulder's fraction of total body height. Each side is evaluated independently; the fit report records the sampled band count, slope, selected pose and whether it used an observed trajectory or a height-prior fallback. The current T-pose threshold is 20 degrees below horizontal.

This applies when fitting a new source rig. It does not migrate existing characters or reinterpret their captured pose matrices. Inspect the exported GLB in rest and in bent poses before selecting it in a consumer.

## Appearance

The UV Bake settings expose **Unobserved Color**, in linear RGB. It supplies color only where no usable source projection exists. The default remains neutral gray, `(0.18, 0.18, 0.18)`. Choosing a fabric color avoids gray patches becoming visible when a limb moves. The corresponding samples retain their fallback flag and zero selected source count; inferred fill never increases observed coverage.

Generated views can disagree about small features. The sample recipe prefers its first-sheet cardinal views, rather than blending several mismatched eyes together. This is a declared appearance policy for the cached dataset, not a general calibration claim:

- front and back weights: 16;
- side weights: 4;
- diagonal weights: 1;
- one best visible contributor per sample;
- same 512² texture and UV coordinates as the baseline.

With `--cardinal-priority`, the recipe derives the unobserved fabric color from the median opaque RGB in the front view's declared torso window, UV `(0.4, 0.4)` to `(0.6, 0.7)`. The report retains the window, color and sample count. These are inferred colors for unobserved areas. The engine's standard projection and bake APIs do the work; no drawing or image generation is performed by the recipe.

## Reproduce and compare

Use a cached eight-view manifest whose camera/image conventions already match the native projector. ImageGen cells at equal orthographic scale need the registered frame described by that manifest; raw cell yaw labels are not sufficient.

```powershell
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_stylized_dummy_quality.py -- --source-blend SOURCE.blend --source-sha256 SHA256 --dataset dataset-native-frame.json --output output/finish-trial --cardinal-priority
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_stylized_dummy_poses.py -- --trials output/finish-trial --output output/finish-poses
```

The four outputs separate the pinned baseline, appearance-only change, arm-fitting-only change and their combination. Appearance-only trials must preserve the original bones and weights exactly. Each GLB is exported through the standard MeshVenn adapter with rest/weight roundtrip checks. Pose evidence uses exact GLB reimports, fixed cameras and the baseline's joint neighborhoods for all candidates.

Local edge distortion, transport fidelity and successful movement are separate observations. None establishes anatomical correctness or consumer acceptance. The generated source has no known 3D ground truth; direct Stytch integration still requires its modular partition, sockets and consumer pose review.
