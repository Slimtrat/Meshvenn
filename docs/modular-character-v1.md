# Modular character contract V1

Meshvenn can optionally export independently renderable skinned regions and
author-declared sockets. This is geometry and attachment authority, **not** a
damage model, equipment system, capability decision, or replacement armature.
The default whole-body GLB route is unchanged.

## Exporting

In Blender's EXPORT settings, enable **Modular Character** and select an authoring
JSON. Headless callers can provide `PipelineContext.metadata["export_modular_spec"]`
as a `ModularCharacterSpec` or its JSON dictionary; alternatively use
`export_modular_manifest_path`. An enabled mode without a valid manifest fails.
Every modular export runs fidelity validation before atomic publication, even if
the ordinary "Verify Export by Reimport" option is disabled.
Authoring JSON rejects duplicate keys at every nesting level and non-finite
numbers. The selected authoring file is protected against overwrite, even when
its filename happens to end in `.glb`.

The authoring document declares:

- `contract: "meshvenn.modular-character"`, `version: 1`, native `rig_id` and
  integer `rig_version` (the fixture retains `canonical-biped-v2`, eighteen joints).
- `coordinates`: right-handed glTF Y-up, +Z-forward, meters, and actual upstream
  height-normalization provenance. The exporter rejects contradictory or unknown
  provenance rather than assuming a height or reconstructing a coordinate frame.
- `regions`: arbitrary stable IDs, semantic roles, and unique exported node names.
  Five regions are illustrated; five is not a limit of the contract.
- `ownership`: exactly one declared region ID for **each original polygon**, in
  mesh polygon order, for every source object. `ownership_source_sha256` hashes the
  ordered local positions and topology so edits invalidate stale face assignments.
- `seams`: `open-shared-vertices`, empty `authoring_changes` and `caps`. V1 copies
  entire existing faces and duplicates shared vertices at intentional open seams;
  it does not cut, cap, weld, remesh, move vertices, or repair skinning.
- `sockets`: stable ID, unique role, owning region, exact native parent-bone name,
  translation, quaternion `[x,y,z,w]`, scale, `frame: "gltf-joint-local"` and
  `units: "meters"`. Transforms are authored values, not inferred equipment offsets.
- Derived `capabilities` describe actual regions/sockets and explicitly declared
  missing roles. Duplicate, ambiguous, dangling, or unsupported declarations fail.

The current Blender implementation certifies the native Canonical Biped V2 rig;
the generic contract does not prescribe five regions or a consumer armature.
V1 refuses shape keys, active non-armature modifiers, loose vertices, more than
four influences, and a region spanning multiple source-object frames. These are
explicit unsupported inputs, not silent loss of geometry or attributes.

### Explicit geometry normalization

`GeometrySurfaceOutput.normalization` is the single height-normalization
authority: a `GeometryNormalization` with the enabled flag, target height,
uniform scale and provenance. `None` means uncertified, not disabled; modular
publication rejects it. The exporter does not search native-specific attributes,
metadata or metrics for coordinate state. Contradictory diagnostic claims fail
validation instead of winning by lookup order.

Native geometry preserves mesh-local projection coordinates, applies the same
non-destructive object scaling and saves `meshvenn_geometry_normalization`.
Historical constructor arguments remain read-only aliases of the explicit
contract. Supported old native `.blend` sources convert their known ID properties
once at the authored-source loading boundary, in memory only. Loading and export
do not silently rewrite an old source. Missing or conflicting saved provenance
requires explicit repair before publication. Existing extent-normalized GLB
routes do not thereby acquire certified height provenance.

`scripts/benchmark_stabilization.py` records source/authoring/baseline/candidate/
pose-set fingerprints and the tested code revision together. It compares the
unchanged doll on all nineteen synchronized poses, including source/raw/reimport
fidelity, using existing thresholds. Its success is behavior preservation, not
posed visual quality or Stytch acceptance; those remain tracked by #60.

## Reading the GLB

The GLB contains an object at `asset.extras.meshvenn_modular_character`:

```json
{
  "spec": { "contract": "meshvenn.modular-character", "version": 1 },
  "bindings": {
    "region_nodes": { "left-arm": 3 },
    "skin": 0,
    "joint_nodes": { "hand.L": 20 },
    "sockets": {
      "attach-left-arm": { "parent_joint_node": 20, "owner_region_node": 3 }
    }
  }
}
```

This is an abbreviated structural example; use the complete embedded document,
not these illustrative indices. References are resolved against the **same GLB**.
Region nodes also expose `meshvenn_region_id` and `meshvenn_region_role` extras.
Every region targets one shared skin, with the original joint names and binds.

Hide a region's mesh node, never delete its bones. Other regions still require the
same skeleton. A socket's world matrix is `joint_world * socket_local_TRS`, including
all inherited scale; the local TRS is not in Blender's display-bone basis. It is
relative to the exported glTF joint. Hide equipment by its declared owning region
if your presentation policy requires it; Meshvenn does not make that gameplay choice.
Metadata-only sockets add **no** skin joints.
Skinned world positions follow `sum(weight * joint_world * inverse_bind) * position`;
do not apply the mesh node's world transform a second time. The native rig may
carry a non-identity parent scale, which remains part of the original skeleton.

## Reproducible generated fixture

Run from the repository root with Blender 5.2.1 and the built native engine:

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/benchmark_modular_character.py -- \
  --resolution 64 --output tmp/modular-fixture
```

The script isolates the CC0 UAL1 source at rest, renders ten calibrated views, and
runs the actual INPUT → native Geometry → UV Bake V2 → canonical V2 Rig → all
43 retargeted Motion clips → modular EXPORT path. No source rig or weights are
passed into reconstruction. The fixture's authoring planes are explicit,
fixture-specific T-pose design choices documented in `partition-authoring.json`;
they are **not** a generic classifier and never inspect dominant bone weights.

Outputs include `character.glb`, packed editable `source.blend`, `authoring.json`,
and a hash-linked `manifest.json` with resolved references and validation evidence.
The source keeps the authoritative whole-body mesh hidden, derived preview parts
visible, and exact authoring/rig/motion catalogues as Blender Text datablocks.
Preview copies are visualization only, not a second surface authority: edit the
original object named in `ownership`, not a visible preview. Position or topology
edits invalidate the ownership hash and require explicit reauthoring; changes to
UVs, materials or normalized weights are exported from that original and checked
against it. Fresh staging copies are temporary and do not overwrite or rename
the existing preview objects.
The hidden original exists only as editable Blender authoring authority; it is
not included as an invisible whole body in the GLB. Only declared regions are
exported as surfaces.

To export this existing source, open `source.blend`, enable **Modular Character**
in EXPORT, and use **Export Authored Source (No Rebuild)**. This dedicated operator
rehydrates the stored native geometry, exact armature and local action catalogue;
it never reruns INPUT, GEOMETRY, rig fitting or retargeting. The ordinary pipeline
Generate button still reconstructs geometry and is not this re-export route.
The fixture uses portable `//character.glb` and `//authoring.json` paths: copy the
whole fixture directory before re-exporting elsewhere. Missing actions, stale
surface ownership or contradictory provenance fail before publication.
The bundle already contains `character.glb` and overwrite is disabled by default.
Choose a new **Output GLB**, or enable **Overwrite Existing** in your working copy
before clicking the re-export button; the distributed artifact is not replaced
silently.
Headless callers use `bpy.ops.bpt.export_existing_modular_source()` after loading
and registering the add-on, or `context_from_authored_scene` in
`implementations.glb_export.modular_source` followed by the regular exporter.

The relocation/re-export CI check can also be reproduced locally:

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_modular_source_smoke.py -- \
  --input-source tmp/modular-fixture/source.blend --output tmp/modular-reopen
```

Editable authority is prepared **before** export: native mesh and rig, declared
face regions and sockets, exact Actions and their catalogue, and provenance.
Source loading reuses the committed catalogue without creating or migrating a
Text. Fresh authoring uses **Prepare Current Modular Source**, or headless
`implementations.authored_source.prepare_authored_source(context)`, after the
Geometry/Rig/Motion stages. Ordinary modular export refuses absent or stale
preparation; it does not initialize the scene or discover unrelated Actions.

Preparation owns any new unreferenced catalogue Text. After fidelity succeeds,
publication commits its references and atomically publishes the GLB. Publication
failure restores previous references and discards the pending Text; existing user
Texts and the previous GLB remain intact. An explicitly static catalogue stores
an empty clip list. Removing existing clips requires explicit re-authoring via
`replace_existing=True`, never an implicit export-time change. Headless callers
that prepare a new catalogue but do not export must call
`context.prepared_modular_source.discard()`.

### Explicit face authoring and older static sources

EXPORT exposes **Load Authored Face Ownership**, **Assign Selected Faces to Region**
and **Save Authored Face Ownership**. Select an original single-user mesh; load a
hash-matching JSON in Object mode, then assign visible whole faces in Object/Edit
mode to an existing region ID. This edits an integer FACE attribute, not geometry,
UVs or weights. Save validates complete ownership and preserves the current JSON's
socket TRS; replacing face edits and overwriting JSON require explicit opt-in.
Derived preview meshes, changed geometry, invalid codes and missing regions fail.

An old unanimated native V2 source without a catalogue can use the separate
**Initialize Old Static V2 Source (No Rebuild)** action. Headless callers explicitly
pass `initialize_static_source=True, binding_method="canonical-envelope-v2"` to
`bpy.ops.bpt.export_existing_modular_source`. This is not a fallback: existing
catalogue references, unsupported bindings, or source/hierarchy/data Actions,
NLA strips and drivers are refused. Only a successful ordinary modular publication
commits the empty catalogue; failed initialization leaves no catalogue or output.

The actual [Stytch workshop doll](../example/v2/modular/StytchDoll/README.md)
demonstrates this route with five regions, eight authored native-local sockets,
18 native joints and **zero clips**. Its source and original two-view bake remain
unchanged. Its fidelity/triangle gates are distinct from the UAL1 appearance and
43-clip fixtures, and from consumer quality certification.

The separate [head-isolated candidate](../example/v2/modular/StytchDollHeadIsolated/README.md)
intentionally edits only head-transition weights, with a new fingerprint and
unchanged geometry, atlas, native rest joints, region ownership and sockets.
Canonical V2 binding uses a persistent closed neck cue; an undoable **Isolate
Head Weights** action exposes the same correction for existing native sources.
Missing evidence leaves the original regional solver unchanged. Seven actual-GLB
head probes and exact rollback/relocation checks are distinct from anatomical
or consumer acceptance. Neck and shoulder/torso quality remain unqualified.

The distinct [authored body-skin candidate](../example/v2/modular/StytchDollAuthoredSkin/README.md)
adds a bounded source correction for #60: adjacent axial influences and explicit
body/limb attachment collars, measured along original polygon edges. **Refine
Authored Body Skin** edits the selected local native source transactionally;
ambiguous ownership, contradictory coincident-seam weights and repeated edits
are refused. Geometry, UVs, atlas, native rests/binds, authored regions and sockets
remain unchanged; distal limb weights remain exact. The corrected source is
prepared by No Rebuild before ordinary export, not repaired by the consumer.

Nineteen exact captured poses gate at least 50% fewer torso edges outside the
original [0.8,1.2] length ratio and 30% lower p95 absolute log strain in each pose,
plus unchanged source/raw/reimport fidelity tolerances. These are improvement
regressions, not visual acceptance: Hall/held shoulder and neck folds remain, and
Stytch has not replayed this selected fingerprint. The original reference, the
head-only candidate, and this candidate have separate hashes and limits. #60 and
#63 remain open; engine/rig/format expansion remains paused.

The separate [shoulder-origin successor](../example/v2/modular/StytchDollShoulderAligned/README.md)
uses **Align Authored Shoulders** to translate only the two upper-arm rest origins
to observed closed body/arm rings, preserving axes, hierarchy, surface, weights
and authored contract. This static-source transaction rejects ambiguous rings,
shared/animated/posed rigs, unsupported socket parents and repeated edits; failure
restores the original datablock exactly. It does not change the default solver.
Because rests intentionally differ, nineteen evidence-only poses are explicitly
derived as `new Rest * inverse(old captured Rest) * old captured Pose`, retaining
immutable capture lineage and the same raw/reimport fidelity gates. Both frozen
shoulder cohorts improve in every pose, but these are not new consumer captures
or visual acceptance. Select and replay its distinct GLB fingerprint in Stytch
before qualifying #60/#63; legacy joint fit, atlas coverage and absent-limb seams
remain documented limitations.

[Captured Hall matrices and their provenance](../example/v2/poses/StytchDoll/README.md)
provide an independent native-source / decoded-GLB / reimport replay for #60.
They reproduce the upstream skin collapse before partitioning, with sub-micrometre
surface agreement. The supplied one-leg snapshot is byte-identical: hiding a
region is not an independent hop pose. The newer
[nineteen synchronized poses](../example/v2/poses/StytchDoll/complete/README.md)
include held, three walk frames, twelve explicit mono-leg hop frames and world
transit. All reproduce upstream distortion with source/raw/reimport agreement
within 1.1 micrometres locally. World transit is a Walk approach, not an explicit
Hop just because of its filename. Corrected source and consumer qualification
are still required; #60 is not resolved by these fidelity/triage checks.

The committed fixture is in `example/v2/modular/UAL1/`. It is a pipeline/fidelity
fixture, not a certification of material coverage, triangle budget, mobile quality,
realistic anatomy, sealed wound caps, or any game-engine runtime.

### Separate appearance inputs

The modular fixture retains the same ten **neutral** geometry inputs, native
resolution 64, eighteen-joint rig and 43 clips. Geometry-finish updates regenerate
the surface ownership hash, GLB and editable source together; old face-ownership
documents must never be paired with a new surface.
Its MATERIAL stage instead receives ten separately rendered source-color views
via the opt-in typed `PipelineContext.material_input: MaterialProjectionInput`.
The image-only contract checks real view/buffer/mask types, finite scene-linear
RGBA, exact camera calibration/alignment and projection frame. It cannot carry a
source mesh, depth or armature. Without it, existing input selection is unchanged.

The isolated source's real Principled Base Color graph is captured as emission
with no lighting or shadows, Standard/sRGB 16-bit PNG and transparent background.
This capture currently rejects non-OPAQUE GLB materials, linked/partial alpha and
unsupported shader graphs; it does not silently flatten them. Source images and
their hashes/provenance are packed into the editable `.blend`. Re-export **No
Rebuild** preserves the baked material; the ordinary Generate button does **not**
rehydrate this separate color input. Regenerate through the CLI above to rebake it.

UV Bake V2 has two production corrections: visibility now uses the same Blender
loop triangles as UV sampling (avoiding false occlusion on nonplanar quads), and
scene-linear RGB is explicitly encoded to portable sRGB RGBA8 (alpha stays linear).
These correct surface sampling/storage, not geometry, rig fitting or their gates.
The atlas remains 512² with 2 samples/axis; the other benchmark settings are unchanged.

Projected sampling additionally filters linear RGB in coverage-associated space
and returns straight RGB, retaining alpha only as source confidence. Transparent
background colors no longer darken opaque baked edges. Image buffers record the
actual RNA association and byte encoding separately from the file's alpha label;
PNG8 sRGB decoding and PNG16/EXR associated-linear handling are tested with real
files. Raw buffer reads stay unchanged. Packed channels, unsupported encodings
and invalid covered pixels fail before MATERIAL modifies UVs or material data.
This does not add runtime transparency or change the region/socket contract.

The contour-aware Organic route also has a separately reported six-pass bounded
micro-finish before its existing final component/orientation/volume safeguards.
It reduces residual voxel bands while trading some contour fit; the original
silhouette, rig and motion gates remain unchanged. The independent 128 humanoid
benchmarks additionally gate true triangle-distance F-score at 1% longest extent
(minimum 0.88), not only the legacy point-sample F-score at 5%. Neither this score
nor connectedness certifies manifold topology or realistic anatomy.

`manifest.appearance` separates real source-view signal, atlas signal, primary/
projected/neutral fallback counts, occupancy and encoding. Counters must agree
with actual bake work. The known non-primary linear RGB (.25,.50,.75) is also
rendered, baked, exported and reimported through actual shaders; its maximum
linear error must stay below .004, the declared RGBA8 transport budget. A white
atlas, missing counters, wrong gamma or substantial neutral fallback cannot pass.
This certifies measured source-color transport, not exact spatial texture recovery
or reconstruction of source roughness/metalness, transparency or PBR lighting.

V2 previews show six states of the final reimported GLB with its SHA/run/attempt.
The modular 64 partition evidence stays distinct from the 128 geometry benchmark;
legacy previews are folded separately. Automatic publishing starts only after
integration on the trusted default branch; artifacts never provide executable
scripts to a write-enabled publishing job. Before integration use the CI summary
and `glb-v2-benchmark-<attempt>` / `glb-v2-preview-<attempt>` artifacts.

## Validation and consumer boundary

Upstream gates check exact face ownership, shared native skeleton, original corner
attributes and materials, normalized skin influences, inverse binds, rest surface,
compound deformation, independent regional visibility, socket transforms, and
rollback without publishing invalid artifacts. Machine-readable evidence states
the actual tolerance and sampling scope; it is not a Godot acceptance result.

Smooth seam normals need special handling: Blender's custom-normal encoding changes
with each region's loop fan. The exporter transports the original source corner
normals through a temporary float-vector attribute, restores those exact values in
the GLB's `NORMAL` accessor, then removes the transport attribute. Raw GLB normals
are checked separately from Blender's reimported normal representation; the UV
budget is not increased to hide normal quantization.
Likewise, source linear RGBA float32 values are transported explicitly for each
vertex-color layer, avoiding Blender's active-color/all-colors channel conversion.
Raw GLB color fidelity is checked separately from the importer's color quantization.

For Blender 5.2.1 verification, decoded smooth-fan normals are not mistaken for
the authoritative accessor values. The verifier independently checks vectors
before the importer's normal codec, then replays the public Mesh encoding API on
an isolated copy and requires a strict match with the imported representation.
It reports source-to-display drift and angle separately. Its temporary recognized
import hook is always restored; an unsupported interface fails closed.

Export parts use the authoritative source's Blender loop triangles, including their
original corner attributes. This fixes non-planar quad/ngon tessellation before
partitioning: reindexing a regional copy cannot silently pick another diagonal.
It is a triangulated representation of the same source surface, not cap geometry.

Stytch/Godot should independently gate import of region IDs, shared skin/joints,
runtime deformation, hiding each limb, and bone-local socket/equipment visibility.
Do not repartition, reconstruct seams, repair weights, guess attachments, or replace
the native eighteen-joint rig with a twenty-joint reference rig in the consumer.
The consumer owns its adapter and gameplay policy, not Meshvenn geometry authority.
