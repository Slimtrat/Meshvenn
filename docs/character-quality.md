# Judge the exported character, including boxy shapes

The character review compares the **actual exported and reimported GLBs** with one original reference. It makes the current shape, lost details and the effect of a finer reconstruction visible. It lives in development tooling; the native engine, runtime API and Stytch contract remain unchanged.

## Open the comparison

In the CI run, download `character-quality-review-<attempt>`, extract the entire archive, and open `review/index.html`. The job summary links the artifact. The page works offline without a server or CDN.

1. Keep the original on the left and select a result on the right.
2. Compare the head, shoulders, torso and feet at 45°, then rotate through front, profile and rear views. Both panels use the same camera and source-defined framing.
3. Select the head or bust close-up. Use **facets** to inspect the actual surface; **materials** shows the appearance imported from each GLB. The silhouette-only reconstructions do not reproduce the original colours.
4. Compare two, eight and ten input views, with and without Organic refinement, then the finer ten-view result. Download the exact GLB shown if you want to inspect it elsewhere.
5. Record your observations in the optional review form. No answer, experience level or approval is filled in for you. The downloaded JSON binds the review to the artifact hashes. An attestation is a personal declaration, not independently verified evidence.

The review does not substitute an unrelated good-looking reference for the reconstruction. A separate reference, when supplied through the rendering API, remains explicitly distinct.

Both visual modes use Cycles CPU, without denoising. The facets mode applies a plain material and flat polygon normals; it does not change mesh vertices. No GPU, Workbench or EGL library is needed on a headless CI runner.

## Generate a new comparison

Use Python 3.11+ and a supported Blender executable with GLB import/export, plus a built native library:

```powershell
python scripts/qualify_character_quality.py `
  --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" `
  --native-library "path/to/bpt_core.dll" `
  --output "tmp/my-character-review"
```

The output directory must be new. The default source is the project-authored, GPL-licensed frozen robot at `tests/fixtures/diagnostics/provider-v1/original-reference.glb`; it is never overwritten. The pipeline uses actual native Visual Hull, Surface Nets and existing Organic refinement:

| Candidates | Grid | Silhouette raster |
| --- | --- | --- |
| 2, 8 and 10 views, each without/with Organic | 64 | 256 |
| 10 views, without/with Organic | 128 | 512 |

Ten views include top and bottom. The fixed native transform maps the grid back to the source frame; candidates are never fitted or independently normalized. A supplied `--source-glb` must already fit the normalized cube `[-1, +1]`; out-of-frame sources are rejected rather than silently rescaled. Other sources do not inherit robot-specific semantic regions.

`--standard-only` omits the finer pair; `--render-size 512` reduces image size. `--from-reconstruction path/to/manifest.json` can be repeated to compare cached actual reconstructions. Their files, original case records and source hashes are checked, then all selected GLBs are imported and rendered again. Reports explicitly distinguish cached reconstruction evidence from a newly executed native reconstruction. An explicit source must match the cached source.

To review existing deliveries directly, `scripts.character_quality.render.render_comparison` accepts one source, candidates and optional separate references, each with its GLB SHA256. `write_presentation` produces the same offline visual review. It does not invent reconstruction/fidelity evidence for arbitrary assets.

## What the checks mean

`assessment.json` reports source-relative geometric observations, **not a universal aesthetic score**:

- Area-weighted planar patches, rotation-invariant normal moments and concentration of section turns help expose squared-off geometry. Analytic ellipsoid/rounded-box/box controls and their thresholds are frozen in `tests/fixtures/character-quality/analytic-v1.json`. Different signals and local regions remain separate; smoothing normals cannot change their input vertices.
- For the exact frozen robot, regions come from the archived original import proof. The antenna also has a source-only probe in the middle half of the free gap between head and tip, intersected with the original stem bounds. This avoids counting the head or tip as the missing stem. No candidate determines this probe. Surface absence is an observed spatial failure; surface presence does not certify semantic identity.
- Surface fidelity uses triangle distances in one **source-defined** frame, without candidate fitting. The historical F-score at 5% of source extent remains a coarse technical gate. Scores at 0.5%, 1% and 2% expose finer differences and are descriptive, without newly tuned pass thresholds.
- Silhouette IoUs include the ten known cameras and withheld angles 30°, 120°, 210° and 300°. The additional `per-view-min-v1` gate requires every relevant view to reach 0.65, rather than letting a mean hide a bad view. This does not change historical profiles. Coverage remains unknown without bound ten-view input evidence; even then it is not a visibility or semantic certificate.
- GLB parsing checks embedded resources, triangle indices, finite accessors, ranges and budgets using the existing strict reader. Fresh Blender reload, synchronized renders and post-import world-space geometry are separate evidence. Resource validity does not imply good shape or usable animation.

Organic can fragment planar patches without recovering a missing shape, so a low planar-patch score alone is insufficient. Normal moments include all imported triangles, including internal and overlapping surfaces. Volume sums closed connected components; it is not a Boolean union. Open or nonmanifold surfaces leave volume preservation unknown, and unknown checks never become passes through averaging.

## Initial robot observations and limits

The initial Windows/Blender 5.2.1 run reproduces the complaint: two-view reconstruction has a square head and torso even with Organic. Its coarse 5%-distance F-score is about **0.92**, illustrating why that score cannot approve appearance. Ten views improve the silhouette; the 128-grid pair restores thin antenna/pole surfaces that are lost or greatly reduced at 64. Some fine regions and topology still need work. The report does not claim a humanoid redesign, facial detail, rig readiness or animation quality.

The technical pipeline fails on incomplete, stale, modified or mismatched evidence and retains logs and partial artifacts. Visual warnings are reported without pretending that human judgment has occurred. `quality_certification`, human review and animated use remain unknown. Future regression gates can be based on reviewed character examples; the present analytic controls do not define every acceptable art style.

This advances #84, #85 and #91 with a visible, repeatable quality check. It does not close their remaining corpus, corrected-delivery or user-review acceptance criteria. No image provider, paid generation or application screenshot is used.
